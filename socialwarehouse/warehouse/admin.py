from django.contrib import admin

from .models import DimPerson, FactPersonScore, FactVoteHistory


@admin.register(DimPerson)
class DimPersonAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "vendor",
        "vendor_voter_id",
        "last_name",
        "first_name",
        "registration_state",
        "registration_status",
        "is_head_of_household",
    )
    list_filter = ("vendor", "registration_state", "registration_status")
    search_fields = ("vendor_voter_id", "last_name", "first_name", "household_id")
    readonly_fields = ("created_at", "updated_at", "last_loaded_at", "silver_source_path")
    raw_id_fields = ("address",)


@admin.register(FactPersonScore)
class FactPersonScoreAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "score_type", "value", "source_vendor", "methodology_version", "scored_at")
    list_filter = ("source_vendor", "score_type")
    search_fields = ("person__vendor_voter_id", "person__last_name")
    raw_id_fields = ("person",)
    readonly_fields = ("loaded_at",)


@admin.register(FactVoteHistory)
class FactVoteHistoryAdmin(admin.ModelAdmin):
    list_display = ("id", "person", "election_date", "election_type", "voted_method", "source_vendor")
    list_filter = ("election_type", "voted_method", "source_vendor")
    search_fields = ("person__vendor_voter_id", "person__last_name")
    raw_id_fields = ("person",)
    readonly_fields = ("loaded_at",)
    date_hierarchy = "election_date"
