"""
TargetSmart field name -> canonical column mapping for silver.persons.

TS column prefixes (`vb.` / `vb.tsmart_` / `vb.vf_`) are stripped to
produce vendor-neutral canonical names. Anything not in this mapping
is stashed into `vendor_extras` (Map<String,String>) at silver build
time.

If a TS field becomes load-bearing and is queried often, promote it
from `vendor_extras` to a canonical column per
`docs/warehouse-schema-evolution.md` and add an entry here.

The vendor "ts" canonical key in silver.persons.vendor + the
vendor_voter_id sourced from `vb.voterbase_id` form the natural key.
"""

TS_TO_CANONICAL: dict[str, str] = {
    # ── Natural key (handled specially: vendor_voter_id comes from
    # vb.voterbase_id, and the constant vendor='ts' is assigned at
    # silver-build time, not via this map).
    # ── Identity
    "vb.tsmart_first_name": "first_name",
    "vb.tsmart_middle_name": "middle_name",
    "vb.tsmart_last_name": "last_name",
    "vb.tsmart_name_suffix": "name_suffix",
    "vb.voterbase_dob": "dob",
    "vb.voterbase_gender": "gender",
    "vb.voterbase_race": "ethnicity",
    "vb.voterbase_phone_wireless": None,  # intentionally NOT mapped — PII; stays in ts_extras only if operator opts in
    # ── Registration
    "vb.vf_voter_status": "registration_status",
    "vb.vf_source_state": "registration_state",
    "vb.vf_reg_cass_date": "registration_date",
    "vb.vf_party": "party_registration",
    "vb.vf_voter_status_reason": "voter_status_reason",
    # ── Address (vendor-supplied raw)
    "vb.vf_reg_address_1": "vendor_address_line1",
    "vb.vf_reg_address_2": "vendor_address_line2",
    "vb.vf_reg_city": "vendor_city",
    "vb.vf_reg_zip": "vendor_zip",
    "vb.vf_reg_zip4": "vendor_zip4",
    # ── Address (geocoded by TS)
    "vb.tsmart_latitude": "latitude",
    "vb.tsmart_longitude": "longitude",
    # ── Pre-joined geo (TS-shipped district memberships)
    "vb.vf_cd": "cd_geoid",
    "vb.vf_sd": "sldu_geoid",
    "vb.vf_hd": "sldl_geoid",
    "vb.tsmart_county_fips": "county_geoid",
    "vb.tsmart_tract_geoid": "tract_geoid",
    "vb.tsmart_block_group_geoid": "block_group_geoid",
    "vb.vf_zcta_geoid": "zcta_geoid",
    # ── Household
    "vb.tsmart_household_id": "household_id",
    "vb.tsmart_household_size": "household_size",
    "vb.tsmart_is_head_of_household": "is_head_of_household",
}

CANONICAL_FIELDS: set[str] = {v for v in TS_TO_CANONICAL.values() if v is not None}

# vendor_state on the canonical model is the 2-char USPS code shipped by
# TS in vb.vf_source_state. Same source as registration_state. We don't
# add a duplicate mapping; importer copies registration_state into
# vendor_state at silver-build time.
