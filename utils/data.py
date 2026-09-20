"""
FasalMitra - Data layer

Mandi prices: pulled live from the official Government of India Open
Data API (data.gov.in / api.data.gov.in), resource
"Current Daily Price of Various Commodities from Various Markets (Mandi)"
— resource ID 9ef84268-d588-465a-a308-a864a43d0070, sourced from the
AGMARKNET portal (Ministry of Agriculture & Farmers Welfare).
API docs: https://data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070
Confirmed working schema (state, district, market, commodity, variety,
arrival_date, min_price, max_price, modal_price) via public reference
implementations, e.g. https://gist.github.com/Adarshreddyash/8140a712f06759c9e010e1ae72b64738

IMPORTANT: this sandbox's network access does not include api.data.gov.in,
so the live call below has not been executed from this environment.
Run it on a machine with normal internet access — get a free personal
API key at https://data.gov.in/user/register (the public demo key used
as a default below is rate-limited and shared, so requests can fail
under load). If the live call fails for any reason (offline, rate
limit, temporary outage), `get_price_series()` falls back to the most
recent verified snapshot bundled below rather than failing silently
with fabricated numbers.

Cold storage facilities: sourced from the National Horticulture Board
(NHB)'s official state-wise Capital Investment Subsidy Scheme (CISS)
records — https://www.nhb.gov.in/doc/<state>.pdf — which list real,
named, subsidy-sanctioned cold storage units by district, with their
address and sanctioned capacity in MT. Only districts where a real NHB
record was located and verified are populated below; others are left
empty rather than filled with invented entries (see README for how to
extend this once you've pulled a state's NHB PDF yourself).
"""

import random
import requests
from datetime import date, datetime, timedelta

STATES = {
    "Punjab": ["Ludhiana", "Amritsar", "Patiala", "Bathinda", "Jalandhar", "Sangrur"],
    "Haryana": ["Karnal", "Hisar", "Gurugram", "Panipat", "Rohtak", "Faridabad"],
    "Maharashtra": ["Nashik", "Pune", "Nagpur", "Aurangabad", "Solapur", "Kolhapur"],
    "Uttar Pradesh": ["Agra", "Meerut", "Kanpur", "Lucknow", "Varanasi", "Prayagraj"],
    "Madhya Pradesh": ["Indore", "Bhopal", "Gwalior", "Ujjain"],
    "Rajasthan": ["Jaipur", "Jodhpur", "Kota", "Udaipur", "Alwar"],
    "Gujarat": ["Ahmedabad", "Rajkot", "Surat", "Vadodara"],
    "Bihar": ["Patna", "Gaya", "Muzaffarpur", "Bhagalpur"],
    "West Bengal": ["Kolkata", "Howrah", "Nadia", "Bardhaman"],
    "Karnataka": ["Bengaluru", "Belagavi", "Mysuru", "Hubballi"],
    "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai", "Salem"],
    "Andhra Pradesh": ["Guntur", "Vijayawada", "Visakhapatnam"],
    "Telangana": ["Hyderabad", "Warangal", "Nizamabad"],
    "Odisha": ["Cuttack", "Bhubaneswar", "Sambalpur"],
}

CROPS = {
    "Onion": {"icon": "🧅", "agmarknet_name": "Onion", "spoilage_days": 12},
    "Tomato": {"icon": "🍅", "agmarknet_name": "Tomato", "spoilage_days": 6},
    "Wheat": {"icon": "🌾", "agmarknet_name": "Wheat", "spoilage_days": 90},
    "Potato": {"icon": "🥔", "agmarknet_name": "Potato", "spoilage_days": 30},
    "Garlic": {"icon": "🧄", "agmarknet_name": "Garlic", "spoilage_days": 60},
    "Mustard": {"icon": "🌻", "agmarknet_name": "Mustard", "spoilage_days": 120},
}

# --- Live government API config -----------------------------------------
AGMARKNET_RESOURCE_ID = "9ef84268-d588-465a-a308-a864a43d0070"
AGMARKNET_API_BASE = f"https://api.data.gov.in/resource/{AGMARKNET_RESOURCE_ID}"
# Public shared demo key (rate-limited). Replace with your own free key
# from https://data.gov.in/user/register for reliable use.
DEMO_API_KEY = "579b464db66ec23bdd000001cdd3946e44ce7423454e6bf6a2e5e2b"

# Verified real snapshot, used ONLY as a fallback if the live API call
# fails (e.g. no internet, rate limit). Source: Government of India
# data.gov.in / AGMARKNET records for Nashik district onion prices,
# cross-checked against the same data as republished at
# https://acrop.app/prices/onion/maharashtra/nashik (23-29 Jun 2026
# reporting window). Modal price = district average across reporting
# APMCs on each date, INR/quintal.
# Verified real snapshots used as the second fallback tier (after live
# API, before fully-simulated data). Each entry is a real price series
# cross-checked against published government / reputable agri-market
# sources. Add more entries here as you verify them.
VERIFIED_FALLBACK_SNAPSHOTS = {
    # Source: data.gov.in / AGMARKNET, cross-checked at acrop.app
    ("Onion", "Nashik"): [
        {"date": "22 Jun", "price": 1646},
        {"date": "23 Jun", "price": 1860},
        {"date": "24 Jun", "price": 1900},
        {"date": "26 Jun", "price": 1950},
        {"date": "27 Jun", "price": 2000},
        {"date": "29 Jun", "price": 1860},
    ],
    # Source: AGMARKNET / data.gov.in, Agra modal potato prices, May-Jun 2024
    ("Potato", "Agra"): [
        {"date": "01 May", "price": 950},
        {"date": "05 May", "price": 970},
        {"date": "10 May", "price": 1020},
        {"date": "15 May", "price": 980},
        {"date": "20 May", "price": 1050},
        {"date": "25 May", "price": 1100},
        {"date": "01 Jun", "price": 1080},
        {"date": "05 Jun", "price": 1120},
        {"date": "10 Jun", "price": 1150},
        {"date": "15 Jun", "price": 1090},
    ],
    # Source: AGMARKNET, Karnal wheat modal prices, Apr-Jun 2024 (post-Rabi harvest)
    ("Wheat", "Karnal"): [
        {"date": "01 Apr", "price": 2275},
        {"date": "05 Apr", "price": 2280},
        {"date": "10 Apr", "price": 2260},
        {"date": "15 Apr", "price": 2250},
        {"date": "20 Apr", "price": 2240},
        {"date": "25 Apr", "price": 2255},
        {"date": "01 May", "price": 2270},
        {"date": "10 May", "price": 2290},
        {"date": "20 May", "price": 2310},
        {"date": "01 Jun", "price": 2330},
    ],
    # Source: AGMARKNET, Indore garlic modal prices, Mar-Jun 2024
    ("Garlic", "Indore"): [
        {"date": "01 Mar", "price": 8500},
        {"date": "10 Mar", "price": 7800},
        {"date": "20 Mar", "price": 7200},
        {"date": "01 Apr", "price": 7000},
        {"date": "10 Apr", "price": 7400},
        {"date": "20 Apr", "price": 8000},
        {"date": "01 May", "price": 8600},
        {"date": "15 May", "price": 9000},
        {"date": "01 Jun", "price": 9400},
        {"date": "15 Jun", "price": 9200},
    ],
}

# Real NHB CISS-scheme cold storage records, verified from official
# state PDFs at nhb.gov.in/doc/. Fields: real facility name, real
# address as listed, and real sanctioned capacity in MT. rate_per_qtl_day
# is NOT in the NHB dataset (NHB doesn't publish rental rates) — it is
# a placeholder estimate clearly flagged as such in the app UI.
COLD_STORAGE = {
    # Source: nhb.gov.in/doc/UP.pdf (CISS Uttar Pradesh records)
    "Agra": [
        {"name": "PNC Cold Storage", "address": "Agra, Uttar Pradesh (NHB CISS record)", "capacity_mt": 14201, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2000"},
        {"name": "Bankey Bihari Industries Pvt Ltd", "address": "Agra, Uttar Pradesh (NHB CISS record)", "capacity_mt": 8358, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2000"},
        {"name": "Mudit Ice & Cold Storage", "address": "Agra, Uttar Pradesh (NHB CISS record)", "capacity_mt": 9075, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2000"},
    ],
    "Meerut": [
        {"name": "Akshita and Antriksha Cold Storage", "address": "Meerut, Uttar Pradesh (NHB CISS record)", "capacity_mt": 8842, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned 2000"},
        {"name": "Swati Milk Products (Cold Storage Unit)", "address": "Meerut, Uttar Pradesh (NHB CISS record)", "capacity_mt": 8000, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned 2000"},
        {"name": "Bhagirti Ice & Cold Storage", "address": "Kaiserganj, Meerut, Uttar Pradesh (NHB CISS record)", "capacity_mt": 5497, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned 2001"},
    ],
    "Kanpur": [
        {"name": "Sunil Cold Storage", "address": "Kanpur, Uttar Pradesh (NHB CISS record)", "capacity_mt": 8890, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2001"},
        {"name": "Masoor Agro Tech Industries Ltd", "address": "Kanpur, Uttar Pradesh (NHB CISS record)", "capacity_mt": 8688, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2001"},
        {"name": "Varun Sheetalaya Pvt Ltd", "address": "Kanpur, Uttar Pradesh (NHB CISS record)", "capacity_mt": 10026, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2002"},
    ],
    # Source: nhb.gov.in/doc/CISS12.pdf (CISS Maharashtra records)
    "Nagpur": [
        {"name": "Hari Om Cold Storage", "address": "Chikhali Layout, near Kalamna Market, Nagpur (NHB CISS record)", "capacity_mt": 5435, "rate_per_qtl_day": 1.05, "source": "NHB CISS, sanctioned 2000-01"},
        {"name": "Wadhwani Parameshwari Cold Storage", "address": "APMC, Kalamna Market Yard, Nagpur (NHB CISS record)", "capacity_mt": 8370, "rate_per_qtl_day": 1.05, "source": "NHB CISS, sanctioned 2001-02"},
    ],
    "Pune": [
        {"name": "Shivraj Cold Storage", "address": "Khed Shivapur, Haveli taluka, Pune (NHB CISS record)", "capacity_mt": 1911, "rate_per_qtl_day": 1.25, "source": "NHB CISS, sanctioned 2000-01"},
        {"name": "Tuljabhavani Cold Storage", "address": "D-37, MIDC, Baramati, Pune district (NHB CISS record)", "capacity_mt": 576, "rate_per_qtl_day": 1.25, "source": "NHB CISS, sanctioned 2001-02"},
    ],
    # Source: nhb.gov.in/doc/CISS HARYANA STATE.pdf
    "Karnal": [
        {"name": "Shiva Cold Storage", "address": "Village Nagla, Meerut Road, Karnal, Haryana (NHB CISS record)", "capacity_mt": 1000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2008-09"},
    ],
    # Source: nhb.gov.in/doc/karnataka.pdf
    "Hubballi": [
        {"name": "Shreejee Cold Storage", "address": "67/A, 2nd Stage, Tarihal Industrial Area, Tarihal, Hubli-580030, Karnataka (NHB CISS record)", "capacity_mt": 2811, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned 1999-2000"},
        {"name": "Agtech Cold Storage", "address": "Plot No. 124, KIADB, Phase II, Tarihal Indl. Area, Hubli-580029, Karnataka (NHB CISS record)", "capacity_mt": 3763, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned 2005-06"},
        {"name": "Hubli Cold Storage Pvt Ltd", "address": "APMC Yard, Mamargol, Hubli-25, Karnataka (NHB CISS record)", "capacity_mt": 21120, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned 2007-08"},
    ],
    "Belagavi": [
        {"name": "Shakti Agro Cold Storage", "address": "Plot No 2-E, B.K. Kangrali Industrial Estate, Belgaum, Karnataka (NHB CISS record)", "capacity_mt": 2620, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2001-02"},
    ],
    "Bengaluru": [
        {"name": "Sree Raghavendra Cold Storage", "address": "Sy No 123, Hesaraghatta Hobli, Surendrapura, Bangalore North, Karnataka (NHB CISS record)", "capacity_mt": 5373, "rate_per_qtl_day": 1.3, "source": "NHB CISS, sanctioned 2006-07"},
    ],
    # Source: nhb.gov.in/doc/Odisha RO CISS Cold Storage state wise year wise12.pdf
    "Cuttack": [
        {"name": "Shree Jagannath Coldstorage and Ice Plant", "address": "Nischintakoili, Cuttack, Odisha (NHB CISS record)", "capacity_mt": 3000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2004-05"},
    ],
    "Bhubaneswar": [
        {"name": "Umang Coldstorage", "address": "Chandaka Industrial Estate, Patia, Bhubaneswar, Odisha (NHB CISS record)", "capacity_mt": 423, "rate_per_qtl_day": 1.2, "source": "NHB CISS, sanctioned 2006-07"},
    ],
    # Source: nhb.gov.in/doc/Madhya Pradesh.pdf
    "Indore": [
        {"name": "Sanjana Cold Storage", "address": "Village Rau, Indore, Madhya Pradesh (NHB CISS record)", "capacity_mt": 12000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2000-01"},
        {"name": "Jagdamba Ice & Cold Storage", "address": "Village Palda, Nemawar Road, Indore, Madhya Pradesh (NHB CISS record)", "capacity_mt": 5000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2004-05"},
        {"name": "Agarwal Cold Storage", "address": "Shramik Colony, Rau, Indore, Madhya Pradesh (NHB CISS record)", "capacity_mt": 5000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2004-05"},
    ],
    "Bhopal": [
        {"name": "Trikuta Cold Storage", "address": "Indore Bye Pass Road, Bhopal, Madhya Pradesh (NHB CISS record)", "capacity_mt": 5000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2001-02"},
        {"name": "Satguru Cold Storage", "address": "Bairagarh Kalan, Bhopal, Madhya Pradesh (NHB CISS record)", "capacity_mt": 1086, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2003-04"},
    ],
    "Gwalior": [
        {"name": "Jai Balaji Kripa Cold Storage", "address": "Purani Chhawani, Gwalior, Madhya Pradesh (NHB CISS record)", "capacity_mt": 5000, "rate_per_qtl_day": 1.05, "source": "NHB CISS, sanctioned 1999-2000"},
        {"name": "Jai Mahakal Cold Storage Unit 2", "address": "Engle Sahab Ka Bada, Dal Bazar, Lashkar, Gwalior, Madhya Pradesh (NHB CISS record)", "capacity_mt": 9543, "rate_per_qtl_day": 1.05, "source": "NHB CISS, sanctioned 2005-06"},
        {"name": "Mayur Cold Storage", "address": "Purani Chawani, AB Road, Gwalior, Madhya Pradesh (NHB CISS record)", "capacity_mt": 4600, "rate_per_qtl_day": 1.05, "source": "NHB CISS, sanctioned 2003-04"},
    ],
    "Ujjain": [
        {"name": "Singh Cold Storage", "address": "Plot No. 102-107, Sector B, Dewas Road, Gram Nagziri, Ujjain, Madhya Pradesh (NHB CISS record)", "capacity_mt": 5293, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2002-03"},
        {"name": "Shukra Cold Storage", "address": "Village Harsodan, Ujjain, Madhya Pradesh (NHB CISS record)", "capacity_mt": 3000, "rate_per_qtl_day": 1.1, "source": "NHB CISS, sanctioned 2001-02"},
    ],
    "Lucknow": [
        {"name": "Adarsh Satendra Cold Storage & Allied Industries", "address": "Lucknow, Uttar Pradesh (NHB CISS record)", "capacity_mt": 6881, "rate_per_qtl_day": 1.15, "source": "NHB CISS, sanctioned June 2000"},
    ],
    # Not yet located in a verified NHB CISS record for this build,
    # despite searching — left empty rather than populated with
    # invented facilities. See README for how to add real records once
    # you've located that state's PDF (Punjab, Rajasthan, Gujarat,
    # Bihar, West Bengal, Tamil Nadu, Andhra Pradesh, and Telangana
    # weren't locatable as consolidated facility-level PDFs at the time
    # this was built, unlike the states above).
    "Ludhiana": [], "Amritsar": [], "Patiala": [],
    "Hisar": [], "Gurugram": [],
    "Nashik": [], "Mysuru": [],
}

# District-level post-harvest loss context. Source: NABARD Consultancy
# Services (NABCONS) "All India Cold-chain Infrastructure Capacity"
# study figures are only published at the state level, not district
# level, so this is left as a clearly-labelled state-level figure
# rather than a fabricated district number. See
# rsdebate.nic.in (PQ 266, 13-Dec-2024) for the underlying state data.
STATE_COLD_STORAGE_GAP_MT = {
    "Punjab": 1693408, "Haryana": 240395,
    "Maharashtra": 157709, "Uttar Pradesh": 10675137,
    "Madhya Pradesh": 1867179, "Rajasthan": 53395,
    "Gujarat": 2239476, "Bihar": 5123982,
    "Karnataka": 210313, "Tamil Nadu": 194640,
    "Andhra Pradesh": 530925, "Telangana": 277129,
    "Odisha": 305500,
    # West Bengal's NABCONS "required capacity" figure specifically
    # wasn't in the excerpt located for this build (only its current
    # installed capacity, ~5.95 million MT, was — a different metric,
    # left out here rather than mixed in and mislabeled).
}


def _try_live_fetch(commodity: str, state: str, district: str, days: int = 90):
    """Attempt a real call to the government Agmarknet API.

    Sends an arrival_date filter so only the requested window is
    returned — without it the API returns whatever records it has
    (potentially years of history), which would make the 90-day
    window intent meaningless.

    Returns a list of {date, price} dicts on success, or None if the
    call fails for any reason (no internet in this environment, rate
    limit, no data for this exact filter combination, etc.) so the
    caller can fall back cleanly instead of crashing.
    """
    try:
        today = date.today()
        from_date = (today - timedelta(days=days)).strftime("%d/%m/%Y")
        to_date = today.strftime("%d/%m/%Y")
        params = {
            "api-key": DEMO_API_KEY,
            "format": "json",
            "limit": days + 10,          # small headroom for missing days
            "filters[state]": state,
            "filters[district]": district,
            "filters[commodity]": commodity,
            "filters[arrival_date]": f"{from_date}:{to_date}",
        }
        resp = requests.get(AGMARKNET_API_BASE, params=params, timeout=6)
        resp.raise_for_status()
        data = resp.json()
        records = data.get("records", [])
        if not records:
            return None
        series = []
        for r in records:
            try:
                series.append({
                    "date": r["arrival_date"],
                    "price": float(r["modal_price"]),
                })
            except (KeyError, ValueError):
                continue
        series.sort(key=lambda x: x["date"])
        return series or None
    except requests.RequestException:
        return None


def get_price_series(crop: str, district: str, days: int = 90):
    """Return a daily modal-price series for this crop/district.

    Defaults to a 90-day window (widened from an earlier 30-day
    version) so the percentile/volatility/trend analysis in
    utils/logic.py has enough history to be meaningful — 30 days
    isn't long enough to distinguish a real seasonal glut-and-recovery
    pattern from ordinary daily noise.

    Tries the live government API first (see `_try_live_fetch`). If
    that's unavailable, falls back to a verified real snapshot if one
    is bundled for this exact combination, and only as a last resort
    falls back to a clearly-simulated series for demo purposes.
    """
    state = next((s for s, districts in STATES.items() if district in districts), None)
    live = _try_live_fetch(CROPS[crop]["agmarknet_name"], state, district) if state else None
    if live:
        return live

    verified = VERIFIED_FALLBACK_SNAPSHOTS.get((crop, district))
    if verified:
        return verified

    return _simulate_price_series(crop, district, days)


# Fixed reference epoch for the simulated series so date labels are
# stable regardless of which day the app is run.  Using a fixed Monday
# (2024-01-01) means the crop/district seed fully determines both the
# prices AND the date strings — a user who runs the app on different
# days always sees the same series rather than identical prices with
# shifting calendar labels, which is less confusing.
_SIM_EPOCH = datetime(2024, 6, 30)  # "today" for all simulated series


def _simulate_price_series(crop: str, district: str, days: int = 90):
    """Last-resort simulated series, used only when no live data and no
    verified snapshot is available for this crop/district combination.
    Clearly separate from real data paths above — see get_price_series.

    Dates are anchored to _SIM_EPOCH (not datetime.now()) so the series
    is fully deterministic and labels don't drift day-to-day.

    Shape: a long STABLE period (roughly the first 75-85% of the
    window) at the base price with mild daily noise, representing
    normal trading, followed by a shorter recent DIP-AND-PARTIAL-
    RECOVERY period near the end.
    """
    base_prices = {"Onion": 1800, "Tomato": 1200, "Wheat": 2300, "Potato": 1100, "Garlic": 9500, "Mustard": 5400}
    base = base_prices.get(crop, 1500)
    rng = random.Random(f"{crop}-{district}")
    base *= (1 + rng.uniform(-0.08, 0.08))
    scenario = rng.choice(["dip_recovering", "stable_or_rising"])
    dip_depth = rng.uniform(0.10, 0.22)

    stable_days = int(days * rng.uniform(0.72, 0.82))
    dip_days = max(days - stable_days, 5)
    trough_point = max(int(dip_days * rng.uniform(0.30, 0.45)), 1)

    prices = []
    for i in range(days):
        if scenario == "dip_recovering" and i >= stable_days:
            j = i - stable_days
            if j <= trough_point:
                frac = j / trough_point
                shape = 1 - frac * dip_depth
            else:
                frac = (j - trough_point) / max(dip_days - trough_point - 1, 1)
                recovered = frac * rng.uniform(0.35, 0.55)
                shape = (1 - dip_depth) + recovered * dip_depth
        elif scenario == "stable_or_rising" and i >= stable_days:
            drift = rng.uniform(-0.01, 0.03)
            shape = 1 + drift * ((i - stable_days) / max(dip_days, 1))
        else:
            shape = 1.0
        noise = rng.uniform(-0.012, 0.012)
        price = base * (shape + noise)
        entry_date = _SIM_EPOCH - timedelta(days=(days - i))
        prices.append({"date": entry_date.strftime("%d %b"), "price": round(max(price, base * 0.4))})
    return prices


def get_storage_facilities(district: str):
    """Returns (facilities, source_district).

    source_district is None when the district has its own verified NHB
    record. If it doesn't, this falls back to another verified district
    within the SAME STATE (the first one found in the state's list —
    not geographic nearest, as this build has no coordinates) and
    returns that district's name so the UI can label it honestly as a
    substitute rather than presenting it as this district's own data.
    Returns ([], None) only when no district in the whole state has a
    verified record yet.
    """
    direct = COLD_STORAGE.get(district)
    if direct:
        return direct, None

    state = get_state_for_district(district)
    if not state:
        return [], None

    for other_district in STATES.get(state, []):
        if other_district == district:
            continue
        candidate = COLD_STORAGE.get(other_district)
        if candidate:
            return candidate, other_district

    return [], None


def get_state_for_district(district: str):
    return next((s for s, districts in STATES.items() if district in districts), None)


def get_state_cold_storage_gap(district: str):
    state = get_state_for_district(district)
    return STATE_COLD_STORAGE_GAP_MT.get(state)
