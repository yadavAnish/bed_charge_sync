import requests
import xml.etree.ElementTree as ET
from requests.auth import HTTPBasicAuth
from odoo import models, fields
from datetime import datetime
import dateutil.parser
import re


import logging

_logger = logging.getLogger(__name__)


class BedSyncLog(models.Model):
    _name = "bed.sync.log"
    _description = "Synced Bed Assignment Encounters"

    encounter_uuid = fields.Char(required=True, unique=True)
    patient_id = fields.Char()
    bed_number = fields.Char()
    fee = fields.Float()
    synced_at = fields.Datetime(default=fields.Datetime.now)
    status = fields.Selection([
        ('success', 'Success'),
        ('failed', 'Failed')
    ])
    message = fields.Text()


class BedSyncEngine(models.Model):
    _name = "bed.sync.engine"
    _description = "Bed Charge Sync Engine"

    def sync_bed_charges(self):
        _logger.info("[START] Bed Charge Sync Started")

        OPENMRS_URL = "http://bahmni-standard-openmrs-1:8080"
        ATOMFEED_URL = f"{OPENMRS_URL}/openmrs/ws/atomfeed/encounter/recent"
        AUTH = HTTPBasicAuth("admin", "Admin123")

        PRODUCT_NAME = "Bed Charges"
        SHOP_ID = 4
        PRICELIST_ID = 1

        try:
            feed_resp = requests.get(ATOMFEED_URL, headers={"Accept": "application/atom+xml"}, auth=AUTH)
            feed_resp.raise_for_status()
            root = ET.fromstring(feed_resp.text)
            ns = {'atom': 'http://www.w3.org/2005/Atom'}
            _logger.info("[PARSE] AtomFeed fetched and parsed successfully")
        except Exception:
            _logger.exception("[ERROR] Fetching or parsing Atomfeed failed")
            return

        for entry in root.findall('atom:entry', ns):
            title = entry.find('atom:title', ns).text if entry.find('atom:title', ns) is not None else ""
            _logger.info("🔎 Title = %s", title)

            if 'Bed-Assignment' not in title:
                continue

            content_elem = entry.find('atom:content', ns)
            content_text = content_elem.text.strip() if content_elem is not None and content_elem.text else ""
            if not content_text:

                _logger.warning("⚠️ Skipping entry with missing content text for Bed-Assignment")
                continue

            content_url = f"{OPENMRS_URL}{content_text}"


            # content_url = f"{OPENMRS_URL}{content_elem.text.strip()}"
            encounter_uuid = content_url.split("/")[-1].split("?")[0]
            _logger.info("📡 Fetching bed assignment from URL: %s", content_url)

            if self.env['bed.sync.log'].search_count([
                ('encounter_uuid', '=', encounter_uuid),
                ('status', '=', 'success')

                ]):
                _logger.info("[SKIP] Already synced: %s", encounter_uuid)
                continue

            try:
                _logger.debug("🌐 Sending GET request to: %s", content_url)
                resp = requests.get(content_url, auth=AUTH)
                _logger.debug("🔁 Response status: %s", resp.status_code)
                resp.raise_for_status()

                try:
                    data = resp.json()
                    _logger.debug("📦 JSON parsed for encounter: %s", encounter_uuid)
                except Exception:
                    _logger.exception("❌ Failed to parse JSON from: %s", content_url)
                    continue

                bed_number = data["bed"]["bedNumber"]
                patient_display = data["patient"]["display"]
                patient_id = patient_display.split(" - ")[0].strip()

                start_dt_raw = data.get("startDatetime")
                end_dt_raw = data.get("endDatetime")

                if not end_dt_raw:
                    _logger.info("[SKIP] Bed assignment %s has no endDatetime", encounter_uuid)
                    continue

                sdt=datetime.strptime(start_dt_raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                start_formatted_date = sdt.strftime("%Y-%m-%d")


                edt=datetime.strptime(end_dt_raw, "%Y-%m-%dT%H:%M:%S.%f%z")
                end_start_formatted_date = edt.strftime("%Y-%m-%d")


                num_days = days_diff = (edt - sdt).days
                if num_days==0:
                    num_days=1
                _logger.error(num_days)

                _logger.info("numdays=%s",num_days)

                if bed_number.startswith("G"):
                    fee = 2000
                elif bed_number.startswith("E"):
                    fee = 5000
                elif bed_number.startswith("P"):
                    fee = 3000
                else:
                    _logger.info("[SKIP] Invalid bed prefix: %s", bed_number)
                    continue


                # Extract display name like: "Anish Kumar Yadav [ABC200000]"
                
                identifier = data["patient"]["display"].split(" - ")[0].strip()
                _logger.info("identifier=%s",identifier)

                if not identifier:
                    raise Exception(f"❌ Could not extract identifier from display: {full_display}")

                _logger.info("🆔 Extracted identifier: %s", identifier)

                # Find partner where ref matches identifier
                partner = self.env['res.partner'].search([('ref', '=', identifier)], limit=1)
                _logger.info(partner.display_name)

                product = self.env['product.product'].search([('name', '=', PRODUCT_NAME)], limit=1)
                _logger.info("product=%s",product)
                if not product:
                    raise Exception(f"Product '{PRODUCT_NAME}' not found")

                order = self.env['sale.order'].create({
                    'partner_id': partner.id,
                    'pricelist_id': PRICELIST_ID,
                    'shop_id': SHOP_ID,
                    'order_line': [(0, 0, {
                        'product_id': product.id,
                        'product_uom_qty': num_days,
                        'price_unit': fee,
                    })]
                })

                _logger.info("[SUCCESS] Created sale.order %s for %s", order.name, patient_id)

                self.env['bed.sync.log'].create({
                    'encounter_uuid': encounter_uuid,
                    'patient_id': patient_id,
                    'bed_number': bed_number,
                    'fee': fee * num_days,
                    'status': 'success',
                    'message': f"Order {order.name} for {num_days} day(s) created"
                })

            except Exception as e:
                _logger.exception("[FAILURE] Encounter %s", encounter_uuid)
                self.env['bed.sync.log'].create({
                    'encounter_uuid': encounter_uuid,
                    'bed_number': bed_number,
                    'status': 'failed',
                    'message': str(e)
                })

        _logger.info("[DONE] Bed Charge Sync Completed")
