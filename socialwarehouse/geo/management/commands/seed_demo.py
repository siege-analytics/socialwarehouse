"""Template-readiness G.1: one-command seed for a state's data across all four domains.

Per G design (#211):
  Q2 = TX as default seed state (overrode my RI recommendation; the
       user wants demographic + economic diversity).
  Q4 = (c) configurable `--states` flag; default TX; users opt into
       multi-state via flag.

Usage:
    python manage.py seed_demo
    python manage.py seed_demo --states TX,CA
    python manage.py seed_demo --states RI --skip economic,civic
    python manage.py seed_demo --dry-run

Wraps the per-domain load commands. Each domain is skippable so a
"just boundaries + ACS" dev setup is one flag away.
"""

from django.core.management import call_command
from django.core.management.base import BaseCommand


# Defaults per G Q2: TX over RI. TX = ~30M population, dozens of CDs,
# 200+ counties, 1000+ school districts, multi-MSA - demos every feature.
DEFAULT_STATES = ["48"]   # Texas state FIPS
ALL_DOMAINS = ["geo", "demographic", "economic", "civic"]

# Per-domain default vintage/sub-args used by seed_demo. Operators
# override individual loads by calling them directly with their own args.
DEFAULT_VINTAGE_ACS = "2019-2023"
DEFAULT_VINTAGE_QCEW = "2024Q3"
DEFAULT_VINTAGE_NCES = "2022-23"
DEFAULT_VINTAGE_NCES_ACS_ENDPOINT = "2018-22"


# State FIPS -> friendly name (used in stdout).
STATE_NAMES = {
    "01": "Alabama", "02": "Alaska", "04": "Arizona", "05": "Arkansas",
    "06": "California", "08": "Colorado", "09": "Connecticut",
    "10": "Delaware", "11": "DC", "12": "Florida", "13": "Georgia",
    "15": "Hawaii", "16": "Idaho", "17": "Illinois", "18": "Indiana",
    "19": "Iowa", "20": "Kansas", "21": "Kentucky", "22": "Louisiana",
    "23": "Maine", "24": "Maryland", "25": "Massachusetts",
    "26": "Michigan", "27": "Minnesota", "28": "Mississippi",
    "29": "Missouri", "30": "Montana", "31": "Nebraska", "32": "Nevada",
    "33": "New Hampshire", "34": "New Jersey", "35": "New Mexico",
    "36": "New York", "37": "North Carolina", "38": "North Dakota",
    "39": "Ohio", "40": "Oklahoma", "41": "Oregon", "42": "Pennsylvania",
    "44": "Rhode Island", "45": "South Carolina", "46": "South Dakota",
    "47": "Tennessee", "48": "Texas", "49": "Utah", "50": "Vermont",
    "51": "Virginia", "53": "Washington", "54": "West Virginia",
    "55": "Wisconsin", "56": "Wyoming",
}


def _name_for(fips):
    return STATE_NAMES.get(fips, f"FIPS {fips}")


class Command(BaseCommand):
    help = (
        "One-command seed for a state's data across the four domains "
        "(geo + demographic + economic + civic). Default state: TX. "
        "Default domains: all four."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--states", type=str, default=",".join(DEFAULT_STATES),
            help=(
                "Comma-separated 2-digit state FIPS codes. Default: 48 (TX). "
                "Examples: '--states 06' (CA), '--states 44,11' (RI + DC)."
            ),
        )
        parser.add_argument(
            "--skip", type=str, default="",
            help=(
                f"Comma-separated domains to skip. Valid: "
                f"{', '.join(ALL_DOMAINS)}. Example: '--skip economic,civic'."
            ),
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Print what each sub-command would do without executing.",
        )

    def handle(self, *args, **options):
        states = [s.strip() for s in options["states"].split(",") if s.strip()]
        skip = set(s.strip() for s in options["skip"].split(",") if s.strip())
        dry_run = options["dry_run"]

        unknown_skip = skip - set(ALL_DOMAINS)
        if unknown_skip:
            self.stdout.write(self.style.ERROR(
                f"Unknown --skip values: {sorted(unknown_skip)}. "
                f"Valid: {ALL_DOMAINS}"
            ))
            return

        domains = [d for d in ALL_DOMAINS if d not in skip]

        self.stdout.write(self.style.SUCCESS(
            f"seed_demo: states={states} ({', '.join(_name_for(s) for s in states)}) "
            f"domains={domains}{' [DRY RUN]' if dry_run else ''}"
        ))

        for state in states:
            self._seed_state(state, domains=domains, dry_run=dry_run)

        self.stdout.write(self.style.SUCCESS("seed_demo: complete."))

    def _seed_state(self, state, *, domains, dry_run):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"=== Seeding {_name_for(state)} (FIPS {state}) ==="
        ))

        if "geo" in domains:
            self._step("assign_boundaries", state, dry_run,
                       year=2020, state_fips=state)

        if "demographic" in domains:
            self._step("load_acs", state, dry_run,
                       vintage=DEFAULT_VINTAGE_ACS, state_fips=state,
                       geography="county")

        if "economic" in domains:
            self._step("load_qcew", state, dry_run,
                       vintage=DEFAULT_VINTAGE_QCEW, state_fips=state)

        if "civic" in domains:
            self._step("load_nces", state, dry_run,
                       vintage=DEFAULT_VINTAGE_NCES, state_fips=state)
            self._step("load_nces_schools", state, dry_run,
                       vintage=DEFAULT_VINTAGE_NCES, state_fips=state)
            self._step("load_nces_edge", state, dry_run,
                       vintage=DEFAULT_VINTAGE_NCES,
                       acs_endpoint=DEFAULT_VINTAGE_NCES_ACS_ENDPOINT,
                       state_fips=state)

    def _step(self, command_name, state, dry_run, **kwargs):
        """Call one sub-command, translating kwargs to the command's CLI args."""
        self.stdout.write(f"  -> {command_name} state={state}")

        if dry_run:
            return

        # Translate kwargs into call_command's expected format.
        cli_kwargs = {}
        if "vintage" in kwargs:
            cli_kwargs["vintage"] = kwargs["vintage"]
        if "year" in kwargs:
            cli_kwargs["year"] = kwargs["year"]
        if "state_fips" in kwargs:
            cli_kwargs["state"] = kwargs["state_fips"]
        if "geography" in kwargs:
            cli_kwargs["geography"] = kwargs["geography"]
        if "acs_endpoint" in kwargs:
            cli_kwargs["acs_endpoint"] = kwargs["acs_endpoint"]

        try:
            call_command(command_name, **cli_kwargs)
        except Exception as exc:
            self.stdout.write(self.style.WARNING(
                f"  -> {command_name} failed: {exc}. Continuing with next step."
            ))
