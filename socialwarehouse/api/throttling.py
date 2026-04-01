from rest_framework.throttling import AnonRateThrottle, UserRateThrottle


class GeocodeThrottle(UserRateThrottle):
    rate = "60/minute"


class BulkExportThrottle(UserRateThrottle):
    rate = "10/minute"
