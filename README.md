# 🌾 FasalMitra — AI Mandi Price & Cold Storage Advisory

Built for the **1M1B AI for Sustainability Virtual Internship** (in collaboration with IBM SkillsBuild & AICTE)

**SDG Alignment:** SDG 2 (Zero Hunger) — primary · SDG 12 (Responsible Consumption & Production), SDG 1 (No Poverty) — secondary
# 🌱 FasalMitra

[🚀 **Live Demo**]([https://fasalmitra.streamlit.app/])

## What it does

FasalMitra helps a smallholder farmer answer one question: *"Should I sell my
crop today, or hold it in cold storage for a few days?"*

1. Shows today's mandi price against a 90-day trend for their crop and district
2. Runs a **percentile / volatility / trend model** (not a fixed threshold — see below) to decide sell-or-wait
3. Calculates a cost-benefit comparison — storage cost vs. potential price recovery
4. Gives a plain-language, source-grounded (RAG) recommendation, in their chosen language, optionally generated live by an LLM (Groq or Claude)
5. Lists nearby cold storage facilities if waiting is worth it
6. Surfaces a state-level post-harvest cold-storage capacity gap (the SDG 12 angle)

## Running it locally

```bash
cd fasalmitra
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`).

## Using the AI-generated explanation (Groq or Claude)

By default the app uses a fast, free, built-in template for the "why this
advice" text — no setup needed. To have that text generated live by an LLM
instead:

1. Open the **"AI explanation settings"** expander on the Check page
2. Pick **Groq** (recommended — free tier, no extra package needed) or
   **Anthropic**
3. Paste your API key into the box that appears

**To embed your key directly in the app** (so you never have to paste it into
the UI): open `utils/config.py` and put it here:

```python
GROQ_API_KEY = "gsk_your_key_here"       # https://console.groq.com/keys
ANTHROPIC_API_KEY = "sk-ant-your_key"    # https://console.anthropic.com
```

The UI box pre-fills from these constants, so once you've set one, picking
that provider in the app just works with no further typing. If the live
call fails for any reason (no key, no internet, rate limit), the app falls
back to the built-in template automatically and shows you why in a caption
— it never crashes and never silently swaps in different content without
saying so.

Groq is called with plain HTTPS (`requests`, already a dependency) using
model `llama-3.3-70b-versatile` — no extra package to install. Anthropic
needs `pip install anthropic` (already in `requirements.txt`).

## The sell-or-wait model

The recommendation used to compare today's price to a flat 30-day average
with a fixed threshold — which barely ever triggered WAIT, because a fixed
percentage means something very different for a low-volatility crop (wheat)
than a high-volatility one (tomato). The current version requires **three
independent signals to agree**, computed over a 90-day window:

1. **Percentile rank** — today's price must be in the bottom quartile of the
   last 90 days, not just below a flat average
2. **Volatility-normalized z-score** — at least half a standard deviation
   below the mean, using *that crop's own* historical volatility
3. **Regression trend** — a proper least-squares slope over the most recent
   ~21 days must be genuinely positive (recovering), not a noisy two-point
   comparison

Only when all three agree, and the projected gain exceeds the estimated
storage cost, does the app recommend waiting. No new dependency is needed —
this is implemented with Python's stdlib `statistics` module plus plain
ordinary-least-squares arithmetic (see `utils/logic.py`, which explains the
formulas in comments).

## Project structure

```
fasalmitra/
├── app.py                  # Main app — top nav, pages, styling, backgrounds
├── requirements.txt
├── assets/                 # Crop background photos (onion.jpg, tomato.jpg, ...)
└── utils/
    ├── config.py            # <- paste your Groq/Anthropic API key here
    ├── translations.py      # UI strings in English + 12 regional languages
    ├── data.py              # Price fetch/fallback + cold storage + states/crops
    ├── logic.py             # Percentile/volatility/trend sell-vs-wait engine
    └── rag.py                # Retrieval-augmented explanation + Groq/Claude calls
```

## Navigation

No sidebar — navigation is a top tab bar (Home / Check My Crop / Find
Storage / About), plus a "Next: ➜" button at the bottom of each page for a
linear step-through, and a **Reset** button (top-right) that clears the
current session's selections and result so the next person can use the app
without seeing anyone else's inputs.

## Backgrounds

- **Home page:** a CSS dark-green ombre gradient, no images needed
- **Check page:** the background photo changes to match whichever crop is
  currently selected (`assets/<crop>.jpg`, base64-embedded at runtime — no
  Streamlit static-file server config needed). A dark overlay + frosted-glass
  card panel keep text and controls readable over busy photos. Add a crop by
  dropping a new photo in `assets/` and adding it to `CROP_IMAGE_FILES` in
  `app.py`.

## Languages

English plus 12 regional languages: हिंदी, ਪੰਜਾਬੀ, বাংলা, मराठी, ગુજરાતી,
தமிழ், తెలుగు, ಕನ್ನಡ, മലയാളം, ଓଡ଼ିଆ, অসমীয়া, اردو — covering the primary
language of the large majority of Indian farmers. The AI advisory text
itself (template or live LLM) is generated natively in each language, not
just UI labels. Source facts (crop storage/seasonal notes) stay in English
in this build; extend `KNOWLEDGE_BASE` in `rag.py` to localize those too.

## Coverage

14 states, 62 districts, 6 crops (Onion, Tomato, Wheat, Potato, Garlic,
Mustard). Price fetching works for any district via the live government API
filter, so adding more states/districts to `STATES` in `utils/data.py` needs
no other changes.

Cold storage is verified for **16 districts across 6 states** — Agra,
Meerut, Kanpur, Lucknow (UP); Pune, Nagpur (Maharashtra); Karnal (Haryana);
Hubballi, Belagavi, Bengaluru (Karnataka); Cuttack, Bhubaneswar (Odisha);
Indore, Bhopal, Gwalior, Ujjain (Madhya Pradesh) — 32 real facility records,
all sourced from official NHB CISS PDFs at `nhb.gov.in/doc/`. Other
districts fall back to the nearest verified district in the *same state* if
one exists, clearly labeled as a substitute; states with no verified record
anywhere (Punjab, Rajasthan, Gujarat, Bihar, West Bengal, Tamil Nadu, Andhra
Pradesh, Telangana) show an honest empty state rather than invented
facilities — no consolidated facility-level NHB PDF for those states was
locatable at the time this was built. Pulling those states' PDFs and adding
them to `COLD_STORAGE` in `utils/data.py` is the way to close that gap.

## Important note on data (read before your demo/submission)

- **Mandi prices** call the live Government of India Open Data API
  (`api.data.gov.in`, resource `9ef84268-d588-465a-a308-a864a43d0070`).
  Falls back to a verified real snapshot, then a clearly-labelled simulated
  series, in that order — the UI always says which one you're looking at.
- **Cold storage facilities and rates:** see Coverage above. Rental rates
  are indicative estimates — NHB's dataset has capacity, not price.
- **Cold storage capacity gap** figures (NABCONS 2015 study) are populated
  for 13 of the 14 states — West Bengal's specific "required capacity"
  figure wasn't locatable in what was accessible for this build.

Be upfront about all of this in your submission's Responsible AI section —
the guideline rewards honesty about limitations, not overclaiming.

## The RAG implementation (for your "how AI is used" section)

`utils/rag.py` implements a genuine retrieve-then-generate pipeline:
1. **Retrieve:** `retrieve(crop)` pulls relevant grounding facts (storage
   behaviour, seasonal pattern, scheme info) from a small curated knowledge
   base — not a generic LLM guess.
2. **Generate:** `generate_explanation()` builds the farmer-facing text from
   those retrieved facts + the calculated numbers, using the template by
   default or a live LLM call (Groq/Claude) when configured — both grounded
   in the same facts, via the same prompt builder (`_build_prompt`), so the
   "Source" box stays meaningful either way.

## Extending it further (optional, if you have time)

- Source more states' NHB cold storage PDFs to close the empty-district gaps
- Add more crops to `utils/data.py` (with matching `KNOWLEDGE_BASE` entries
  in `utils/rag.py` so the RAG grounding stays genuine, not just decorative)
- Add a voice-input option for lower-literacy users
