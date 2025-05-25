{
    'name': 'OpenMRS Bed Assignment Sync',
    'version': '1.0',
    'summary': 'Sync bed-patient assignments from OpenMRS Atomfeed',
    'depends': ['base'],
    'author': 'Anish Kumar Yadav',
    'category': 'Healthcare',
    'installable': True,
    'application': False,
    'data': [
        'data/ir_cron.xml',
        # 'views/bed_assignment_views.xml',
    ],
}
