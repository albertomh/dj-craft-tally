from django.contrib.admin.apps import AdminConfig


class CustomAdminConfig(AdminConfig):
    default_site = "dj_craft_tally.sites.CustomAdminSite"
