from odoo import models, fields


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
