"""
FasalMitra - RAG (Retrieval-Augmented Generation) explanation layer

This is a genuine retrieve-then-generate pipeline, not just an LLM call:

  1. RETRIEVE: given the crop + computed analysis, pull the relevant
     fact snippets from a small curated knowledge base (crop storage
     behaviour, PMFBY/MIDH scheme notes, seasonal pattern notes).
  2. GENERATE: those retrieved snippets are passed as grounding context
     into the explanation template (or, in production, into an LLM
     call — see `generate_with_llm()` below for the drop-in swap) so
     the final farmer-facing text is traceable to a real source.

The retrieved snippet is also shown to the user in the app ("Source"),
which is what makes this auditable/transparent rather than a black box
— directly addressing the Responsible AI 'Transparency' requirement.
"""

KNOWLEDGE_BASE = {
    "Onion": {
        "storage": "Onions store well in ventilated cold storage (0-4°C, 65-70% humidity) for up to 3-4 months with proper curing; poor ventilation causes rapid sprouting and rot.",
        "seasonal": "Onion prices typically dip sharply at peak Rabi harvest arrivals (March-May) and recover as market arrivals thin out over the following 2-3 months.",
        "scheme": "MIDH (Mission for Integrated Development of Horticulture) offers subsidy support for on-farm and cluster-level onion storage structures.",
    },
    "Tomato": {
        "storage": "Tomatoes are highly perishable; cold storage (10-13°C) extends shelf life by only 1-2 weeks even under good conditions — holding beyond that risks significant spoilage.",
        "seasonal": "Tomato prices are highly volatile and can swing 30-50% within days due to short shelf life and weather-sensitive supply — price recovery windows are narrow.",
        "scheme": "State horticulture missions periodically support tomato processing-unit linkages to reduce glut-season wastage.",
    },
    "Wheat": {
        "storage": "Wheat, as a grain crop, stores safely for many months in dry warehouse conditions with minimal quality loss, unlike perishable produce.",
        "seasonal": "Wheat prices tend to be lowest right after the Rabi harvest (April-May) and gradually firm up through the year as government/private procurement absorbs stock.",
        "scheme": "MSP (Minimum Support Price) procurement is available for wheat through government agencies, offering a price floor alternative to open-market sale.",
    },
    "Potato": {
        "storage": "Potatoes store well in cold storage (2-4°C) for several months, though prolonged storage requires careful humidity control to prevent sprouting.",
        "seasonal": "Potato prices typically bottom out during peak harvest arrival and recover over subsequent months as cold-stored stock is released gradually.",
        "scheme": "State cold storage subsidy schemes commonly cover potato-specific storage infrastructure given its status as a staple crop.",
    },
    "Garlic": {
        "storage": "Garlic stores well in cool, dry, well-ventilated conditions (0-5°C, low humidity) for up to 6-7 months after proper curing; excess moisture causes rapid mould and sprouting.",
        "seasonal": "Garlic prices typically dip at Rabi harvest peak (March-April) and often recover significantly over the following months as fresh arrivals taper off.",
        "scheme": "MIDH horticulture cluster schemes extend the same storage subsidy support to garlic as to onion in several producing states.",
    },
    "Mustard": {
        "storage": "Mustard seed, like other oilseeds, stores safely for many months in dry warehouse conditions with minimal quality loss if moisture content is kept low at intake.",
        "seasonal": "Mustard prices tend to be lowest right after Rabi harvest (March-April) and often firm up through the year as government MSP procurement and crushing demand absorb stock.",
        "scheme": "MSP procurement is available for mustard through NAFED and state agencies, offering a price floor alternative to open-market sale.",
    },
}


def retrieve(crop: str) -> dict:
    """Retrieval step: fetch the relevant knowledge snippets for this crop."""
    return KNOWLEDGE_BASE.get(crop, {})


def generate_explanation(crop: str, analysis: dict, lang: str, provider: str = "template", api_key: str = "") -> dict:
    """Generation step: build a grounded, plain-language explanation.

    By default (provider="template") this uses the fast, free,
    deterministic template below — no API key needed, works offline,
    and is what the internship deliverable can rely on without any
    setup. Pass provider="groq" or provider="anthropic" with a real
    api_key to have the explanation itself written live by that
    model instead, grounded in the same retrieved facts; if that call
    fails for any reason, this falls back to the template automatically
    and reports the failure reason so the caller can show it rather
    than silently swapping content.

    Returns the farmer-facing text, the source snippet used (for the
    "Source" box), and llm_status — None when the template was used by
    default, or a dict with used_llm/provider/error when a live call
    was attempted — so the app can be transparent about which one
    produced what the person is reading.
    """
    facts = retrieve(crop)
    storage_fact = facts.get("storage", "")
    seasonal_fact = facts.get("seasonal", "")

    key = "wait" if analysis["should_wait"] else "sell"
    template_source = storage_fact + " " + seasonal_fact

    # Build ONLY the template for the requested language (fall back to
    # English) — not all 13 at once.  Each entry is a plain dict so the
    # f-strings are evaluated lazily here rather than for every language.
    _tmpl_map = {
        "English": {
            "wait": (
                f"{crop} prices in your area are currently {abs(analysis['pct_vs_avg'])}% "
                f"below the 90-day average, and the recent trend is upward. Based on typical "
                f"seasonal patterns for {crop.lower()}, prices could recover to around "
                f"₹{analysis['projected_price']}/quintal over the next {analysis['suggested_days']} days. "
                f"Estimated storage cost for your quantity is ₹{analysis['storage_cost']}, against a "
                f"potential gain of ₹{analysis['potential_gain']} — a net benefit of ₹{analysis['net_benefit']}. "
                f"{storage_fact}"
            ),
            "sell": (
                f"{crop} prices in your area are currently at or above the 90-day average "
                f"(₹{analysis['today_price']} vs ₹{analysis['avg_price']} average), or the trend doesn't "
                f"favour waiting. Holding stock further carries storage cost and spoilage risk without a "
                f"clear price upside right now. {storage_fact}"
            ),
        },
        "हिंदी": {
            "wait": (
                f"आपके क्षेत्र में {crop} की कीमत 90-दिन के औसत से {abs(analysis['pct_vs_avg'])}% कम है, "
                f"और हाल का रुझान ऊपर की ओर है। सामान्य मौसमी पैटर्न के अनुसार, अगले "
                f"{analysis['suggested_days']} दिनों में कीमत लगभग ₹{analysis['projected_price']}/क्विंटल तक जा सकती है। "
                f"आपकी मात्रा के लिए अनुमानित भंडारण लागत ₹{analysis['storage_cost']} है, जबकि संभावित लाभ "
                f"₹{analysis['potential_gain']} है — यानी शुद्ध लाभ ₹{analysis['net_benefit']}।"
            ),
            "sell": (
                f"आपके क्षेत्र में {crop} की कीमत 90-दिन के औसत के बराबर या उससे अधिक है "
                f"(₹{analysis['today_price']} बनाम ₹{analysis['avg_price']} औसत), या रुझान इंतज़ार के पक्ष में नहीं है। "
                f"अभी और रोकने से भंडारण लागत और खराब होने का जोखिम है, बिना स्पष्ट कीमत लाभ के।"
            ),
        },
        "ਪੰਜਾਬੀ": {
            "wait": (
                f"ਤੁਹਾਡੇ ਖੇਤਰ ਵਿੱਚ {crop} ਦੀ ਕੀਮਤ 90-ਦਿਨ ਦੀ ਔਸਤ ਤੋਂ {abs(analysis['pct_vs_avg'])}% ਘੱਟ ਹੈ, "
                f"ਅਤੇ ਹਾਲ ਦਾ ਰੁਝਾਨ ਉੱਪਰ ਵੱਲ ਹੈ। ਆਮ ਮੌਸਮੀ ਪੈਟਰਨ ਦੇ ਅਨੁਸਾਰ, ਅਗਲੇ "
                f"{analysis['suggested_days']} ਦਿਨਾਂ ਵਿੱਚ ਕੀਮਤ ਲਗਭਗ ₹{analysis['projected_price']}/ਕੁਇੰਟਲ ਤੱਕ ਜਾ ਸਕਦੀ ਹੈ। "
                f"ਤੁਹਾਡੀ ਮਾਤਰਾ ਲਈ ਅਨੁਮਾਨਿਤ ਸਟੋਰੇਜ ਲਾਗਤ ₹{analysis['storage_cost']} ਹੈ, ਜਦਕਿ ਸੰਭਾਵੀ ਲਾਭ "
                f"₹{analysis['potential_gain']} ਹੈ — ਯਾਨੀ ਸ਼ੁੱਧ ਲਾਭ ₹{analysis['net_benefit']}।"
            ),
            "sell": (
                f"ਤੁਹਾਡੇ ਖੇਤਰ ਵਿੱਚ {crop} ਦੀ ਕੀਮਤ 90-ਦਿਨ ਦੀ ਔਸਤ ਦੇ ਬਰਾਬਰ ਜਾਂ ਵੱਧ ਹੈ, "
                f"ਜਾਂ ਰੁਝਾਨ ਉਡੀਕ ਦੇ ਹੱਕ ਵਿੱਚ ਨਹੀਂ ਹੈ। ਹੋਰ ਰੋਕਣ ਨਾਲ ਸਟੋਰੇਜ ਲਾਗਤ ਅਤੇ ਖਰਾਬ ਹੋਣ ਦਾ ਖ਼ਤਰਾ ਹੈ।"
            ),
        },
        "বাংলা": {
            "wait": (
                f"আপনার এলাকায় {crop} এর দাম বর্তমানে 90-দিনের গড় থেকে {abs(analysis['pct_vs_avg'])}% কম, "
                f"এবং সাম্প্রতিক প্রবণতা ঊর্ধ্বমুখী। সাধারণ মৌসুমী প্যাটার্ন অনুযায়ী, আগামী "
                f"{analysis['suggested_days']} দিনে দাম প্রায় ₹{analysis['projected_price']}/কুইন্টাল পর্যন্ত পুনরুদ্ধার হতে পারে। "
                f"আপনার পরিমাণের জন্য আনুমানিক সংরক্ষণ খরচ ₹{analysis['storage_cost']}, বিপরীতে সম্ভাব্য লাভ "
                f"₹{analysis['potential_gain']} — অর্থাৎ নিট লাভ ₹{analysis['net_benefit']}।"
            ),
            "sell": (
                f"আপনার এলাকায় {crop} এর দাম বর্তমানে 90-দিনের গড়ের সমান বা তার বেশি "
                f"(₹{analysis['today_price']} বনাম ₹{analysis['avg_price']} গড়), অথবা প্রবণতা অপেক্ষার পক্ষে নয়। "
                f"আরও ধরে রাখলে সংরক্ষণ খরচ ও নষ্ট হওয়ার ঝুঁকি থাকে, স্পষ্ট মূল্য লাভ ছাড়াই।"
            ),
        },
        "मराठी": {
            "wait": (
                f"तुमच्या भागात {crop} ची किंमत सध्या 90-दिवसांच्या सरासरीपेक्षा {abs(analysis['pct_vs_avg'])}% कमी आहे, "
                f"आणि अलीकडचा कल वाढता आहे. नेहमीच्या हंगामी पद्धतीनुसार, पुढील "
                f"{analysis['suggested_days']} दिवसांत किंमत सुमारे ₹{analysis['projected_price']}/क्विंटलपर्यंत वाढू शकते. "
                f"तुमच्या प्रमाणासाठी अंदाजे साठवण खर्च ₹{analysis['storage_cost']} आहे, तर संभाव्य फायदा "
                f"₹{analysis['potential_gain']} आहे — म्हणजे निव्वळ फायदा ₹{analysis['net_benefit']}."
            ),
            "sell": (
                f"तुमच्या भागात {crop} ची किंमत सध्या 90-दिवसांच्या सरासरीइतकी किंवा त्याहून अधिक आहे "
                f"(₹{analysis['today_price']} विरुद्ध ₹{analysis['avg_price']} सरासरी), किंवा कल थांबण्याच्या बाजूने नाही. "
                f"आणखी थांबल्यास साठवण खर्च आणि खराब होण्याचा धोका आहे, स्पष्ट किंमत फायद्याशिवाय."
            ),
        },
        "ગુજરાતી": {
            "wait": (
                f"તમારા વિસ્તારમાં {crop} ની કિંમત હાલમાં 90-દિવસની સરેરાશ કરતાં {abs(analysis['pct_vs_avg'])}% ઓછી છે, "
                f"અને તાજેતરનો વલણ ઉપર તરફ છે. સામાન્ય મોસમી પેટર્ન મુજબ, આગામી "
                f"{analysis['suggested_days']} દિવસોમાં કિંમત આશરે ₹{analysis['projected_price']}/ક્વિન્ટલ સુધી પાછી આવી શકે છે. "
                f"તમારા જથ્થા માટે અંદાજિત સંગ્રહ ખર્ચ ₹{analysis['storage_cost']} છે, જ્યારે સંભવિત લાભ "
                f"₹{analysis['potential_gain']} છે — એટલે કે ચોખ્ખો લાભ ₹{analysis['net_benefit']}."
            ),
            "sell": (
                f"તમારા વિસ્તારમાં {crop} ની કિંમત હાલમાં 90-દિવસની સરેરાશ જેટલી અથવા વધુ છે "
                f"(₹{analysis['today_price']} વિરુદ્ધ ₹{analysis['avg_price']} સરેરાશ), અથવા વલણ રાહ જોવાની તરફેણમાં નથી. "
                f"વધુ રોકવાથી સંગ્રહ ખર્ચ અને બગડવાનું જોખમ છે, સ્પષ્ટ કિંમત લાભ વિના."
            ),
        },
        "தமிழ்": {
            "wait": (
                f"உங்கள் பகுதியில் {crop} விலை தற்போது 90-நாள் சராசரியை விட {abs(analysis['pct_vs_avg'])}% குறைவாக உள்ளது, "
                f"சமீபத்திய போக்கு மேல்நோக்கி உள்ளது. வழக்கமான பருவகால முறையின்படி, அடுத்த "
                f"{analysis['suggested_days']} நாட்களில் விலை சுமார் ₹{analysis['projected_price']}/குவிண்டால் வரை மீண்டும் உயரலாம். "
                f"உங்கள் அளவுக்கான மதிப்பிடப்பட்ட சேமிப்பு செலவு ₹{analysis['storage_cost']}, சாத்தியமான ஆதாயம் "
                f"₹{analysis['potential_gain']} — அதாவது நிகர பயன் ₹{analysis['net_benefit']}."
            ),
            "sell": (
                f"உங்கள் பகுதியில் {crop} விலை தற்போது 90-நாள் சராசரிக்கு சமமாகவோ அதிகமாகவோ உள்ளது "
                f"(₹{analysis['today_price']} எதிராக ₹{analysis['avg_price']} சராசரி), அல்லது போக்கு காத்திருப்பதற்கு ஆதரவாக இல்லை. "
                f"மேலும் வைத்திருப்பது தெளிவான விலை ஆதாயம் இல்லாமல் சேமிப்பு செலவு மற்றும் கெட்டுப்போகும் அபாயத்தை ஏற்படுத்தும்."
            ),
        },
        "తెలుగు": {
            "wait": (
                f"మీ ప్రాంతంలో {crop} ధర ప్రస్తుతం 90-రోజుల సగటు కంటే {abs(analysis['pct_vs_avg'])}% తక్కువగా ఉంది, "
                f"ఇటీవలి ధోరణి పైకి ఉంది. సాధారణ కాలానుగుణ నమూనా ప్రకారం, రాబోయే "
                f"{analysis['suggested_days']} రోజుల్లో ధర సుమారు ₹{analysis['projected_price']}/క్వింటాల్ వరకు కోలుకోవచ్చు. "
                f"మీ పరిమాణానికి అంచనా నిల్వ ఖర్చు ₹{analysis['storage_cost']}, సంభావ్య లాభం "
                f"₹{analysis['potential_gain']} — అంటే నికర ప్రయోజనం ₹{analysis['net_benefit']}."
            ),
            "sell": (
                f"మీ ప్రాంతంలో {crop} ధర ప్రస్తుతం 90-రోజుల సగటుతో సమానంగా లేదా అంతకంటే ఎక్కువగా ఉంది "
                f"(₹{analysis['today_price']} vs ₹{analysis['avg_price']} సగటు), లేదా ధోరణి వేచి ఉండటానికి అనుకూలంగా లేదు. "
                f"మరింత నిల్వ చేయడం స్పష్టమైన ధర ప్రయోజనం లేకుండా నిల్వ ఖర్చు మరియు చెడిపోయే ప్రమాదాన్ని కలిగిస్తుంది."
            ),
        },
        "ಕನ್ನಡ": {
            "wait": (
                f"ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ {crop} ಬೆಲೆ ಪ್ರಸ್ತುತ 90-ದಿನಗಳ ಸರಾಸರಿಗಿಂತ {abs(analysis['pct_vs_avg'])}% ಕಡಿಮೆಯಿದೆ, "
                f"ಇತ್ತೀಚಿನ ಪ್ರವೃತ್ತಿ ಏರುಗತಿಯಲ್ಲಿದೆ. ಸಾಮಾನ್ಯ ಋತುಮಾನ ಮಾದರಿಯ ಪ್ರಕಾರ, ಮುಂದಿನ "
                f"{analysis['suggested_days']} ದಿನಗಳಲ್ಲಿ ಬೆಲೆ ಸುಮಾರು ₹{analysis['projected_price']}/ಕ್ವಿಂಟಲ್‌ಗೆ ಚೇತರಿಸಿಕೊಳ್ಳಬಹುದು. "
                f"ನಿಮ್ಮ ಪ್ರಮಾಣಕ್ಕೆ ಅಂದಾಜು ಶೇಖರಣಾ ವೆಚ್ಚ ₹{analysis['storage_cost']}, ಸಂಭಾವ್ಯ ಲಾಭ "
                f"₹{analysis['potential_gain']} — ಅಂದರೆ ನಿವ್ವಳ ಲಾಭ ₹{analysis['net_benefit']}."
            ),
            "sell": (
                f"ನಿಮ್ಮ ಪ್ರದೇಶದಲ್ಲಿ {crop} ಬೆಲೆ ಪ್ರಸ್ತುತ 90-ದಿನಗಳ ಸರಾಸರಿಗೆ ಸಮಾನ ಅಥವಾ ಹೆಚ್ಚಿದೆ "
                f"(₹{analysis['today_price']} ವಿರುದ್ಧ ₹{analysis['avg_price']} ಸರಾಸರಿ), ಅಥವಾ ಪ್ರವೃತ್ತಿ ಕಾಯುವಿಕೆಯ ಪರವಾಗಿಲ್ಲ. "
                f"ಇನ್ನಷ್ಟು ಇಟ್ಟುಕೊಳ್ಳುವುದು ಸ್ಪಷ್ಟ ಬೆಲೆ ಲಾಭವಿಲ್ಲದೆ ಶೇಖರಣಾ ವೆಚ್ಚ ಮತ್ತು ಹಾಳಾಗುವ ಅಪಾಯವನ್ನು ಹೊಂದಿದೆ."
            ),
        },
        "മലയാളം": {
            "wait": (
                f"നിങ്ങളുടെ പ്രദേശത്ത് {crop} വില നിലവിൽ 90-ദിവസ ശരാശരിയേക്കാൾ {abs(analysis['pct_vs_avg'])}% കുറവാണ്, "
                f"സമീപകാല ട്രെൻഡ് മുകളിലേക്കാണ്. സാധാരണ സീസണൽ പാറ്റേൺ അനുസരിച്ച്, അടുത്ത "
                f"{analysis['suggested_days']} ദിവസങ്ങളിൽ വില ഏകദേശം ₹{analysis['projected_price']}/ക്വിന്റൽ വരെ തിരിച്ചുവരാം. "
                f"നിങ്ങളുടെ അളവിനുള്ള കണക്കാക്കിയ സംഭരണ ചെലവ് ₹{analysis['storage_cost']}, സാധ്യതയുള്ള നേട്ടം "
                f"₹{analysis['potential_gain']} — അതായത് അറ്റ നേട്ടം ₹{analysis['net_benefit']}."
            ),
            "sell": (
                f"നിങ്ങളുടെ പ്രദേശത്ത് {crop} വില നിലവിൽ 90-ദിവസ ശരാശരിക്ക് തുല്യമോ അതിലധികമോ ആണ് "
                f"(₹{analysis['today_price']} vs ₹{analysis['avg_price']} ശരാശരി), അല്ലെങ്കിൽ ട്രെൻഡ് കാത്തിരിക്കുന്നതിന് അനുകൂലമല്ല. "
                f"കൂടുതൽ സൂക്ഷിക്കുന്നത് വ്യക്തമായ വില നേട്ടമില്ലാതെ സംഭരണ ചെലവും കേടുപാടും ഉണ്ടാക്കും."
            ),
        },
        "ଓଡ଼ିଆ": {
            "wait": (
                f"ଆପଣଙ୍କ ଅଞ୍ଚଳରେ {crop} ର ମୂଲ୍ୟ ବର୍ତ୍ତମାନ 90-ଦିନିଆ ହାରାହାରିଠାରୁ {abs(analysis['pct_vs_avg'])}% କମ୍ ଅଛି, "
                f"ଏବଂ ସାମ୍ପ୍ରତିକ ଧାରା ଉପରମୁଖୀ। ସାଧାରଣ ଋତୁକାଳୀନ ଢାଞ୍ଚା ଅନୁଯାୟୀ, ଆଗାମୀ "
                f"{analysis['suggested_days']} ଦିନରେ ମୂଲ୍ୟ ପ୍ରାୟ ₹{analysis['projected_price']}/କ୍ୱିଣ୍ଟାଲ୍ ପର୍ଯ୍ୟନ୍ତ ପୁନରୁଦ୍ଧାର ହୋଇପାରେ। "
                f"ଆପଣଙ୍କ ପରିମାଣ ପାଇଁ ଆକଳିତ ଷ୍ଟୋରେଜ୍ ଖର୍ଚ୍ଚ ₹{analysis['storage_cost']}, ସମ୍ଭାବ୍ୟ ଲାଭ "
                f"₹{analysis['potential_gain']} — ଅର୍ଥାତ୍ ନିଟ୍ ଲାଭ ₹{analysis['net_benefit']}।"
            ),
            "sell": (
                f"ଆପଣଙ୍କ ଅଞ୍ଚଳରେ {crop} ର ମୂଲ୍ୟ ବର୍ତ୍ତମାନ 90-ଦିନିଆ ହାରାହାରି ସହ ସମାନ କିମ୍ବା ଅଧିକ "
                f"(₹{analysis['today_price']} ବନାମ ₹{analysis['avg_price']} ହାରାହାରି), କିମ୍ବା ଧାରା ଅପେକ୍ଷା ପକ୍ଷରେ ନାହିଁ। "
                f"ଅଧିକ ରଖିଲେ ସ୍ପଷ୍ଟ ମୂଲ୍ୟ ଲାଭ ବିନା ଷ୍ଟୋରେଜ୍ ଖର୍ଚ୍ଚ ଏବଂ ନଷ୍ଟ ହେବାର ବିପଦ ରହିଛି।"
            ),
        },
        "অসমীয়া": {
            "wait": (
                f"আপোনাৰ অঞ্চলত {crop} ৰ দাম বৰ্তমান ৯০-দিনৰ গড়তকৈ {abs(analysis['pct_vs_avg'])}% কম, "
                f"আৰু শেহতীয়া প্ৰৱণতা ওপৰলৈ গৈ আছে। সাধাৰণ ঋতুকালীন প্ৰতিৰূপ অনুসৰি, অহা "
                f"{analysis['suggested_days']} দিনত দাম প্ৰায় ₹{analysis['projected_price']}/কুইণ্টললৈকে পুনৰুদ্ধাৰ হ'ব পাৰে। "
                f"আপোনাৰ পৰিমাণৰ বাবে আনুমানিক ভঁৰাল খৰচ ₹{analysis['storage_cost']}, সম্ভাৱ্য লাভ "
                f"₹{analysis['potential_gain']} — অৰ্থাৎ নিট লাভ ₹{analysis['net_benefit']}।"
            ),
            "sell": (
                f"আপোনাৰ অঞ্চলত {crop} ৰ দাম বৰ্তমান ৯০-দিনৰ গড়ৰ সমান বা তাতকৈ বেছি "
                f"(₹{analysis['today_price']} বনাম ₹{analysis['avg_price']} গড়), বা প্ৰৱণতা অপেক্ষাৰ পক্ষে নহয়। "
                f"অধিক ৰখাত স্পষ্ট দাম লাভ নোহোৱাকৈ ভঁৰাল খৰচ আৰু নষ্ট হোৱাৰ আশংকা থাকে।"
            ),
        },
        "اردو": {
            "wait": (
                f"آپ کے علاقے میں {crop} کی قیمت اس وقت 90 دن کی اوسط سے {abs(analysis['pct_vs_avg'])}% کم ہے، "
                f"اور حالیہ رجحان اوپر کی طرف ہے۔ عام موسمی پیٹرن کے مطابق، اگلے "
                f"{analysis['suggested_days']} دنوں میں قیمت تقریباً ₹{analysis['projected_price']}/کوئنٹل تک بحال ہو سکتی ہے۔ "
                f"آپ کی مقدار کے لیے متوقع اسٹوریج لاگت ₹{analysis['storage_cost']} ہے، جبکہ ممکنہ فائدہ "
                f"₹{analysis['potential_gain']} ہے — یعنی خالص فائدہ ₹{analysis['net_benefit']}۔"
            ),
            "sell": (
                f"آپ کے علاقے میں {crop} کی قیمت اس وقت 90 دن کی اوسط کے برابر یا اس سے زیادہ ہے "
                f"(₹{analysis['today_price']} بمقابلہ ₹{analysis['avg_price']} اوسط)، یا رجحان انتظار کے حق میں نہیں ہے۔ "
                f"مزید روکنے سے واضح قیمت کے فائدے کے بغیر اسٹوریج لاگت اور خراب ہونے کا خطرہ ہے۔"
            ),
        },
    }

    lang_entry = _tmpl_map.get(lang, _tmpl_map["English"])
    template_text = lang_entry[key]
    template_source = storage_fact + " " + seasonal_fact

    if provider in ("groq", "anthropic"):
        llm_result = generate_with_llm(crop, analysis, lang, provider, api_key)
        if llm_result["used_llm"]:
            return {
                "explanation": llm_result["explanation"],
                "source_snippet": llm_result["source_snippet"],
                "llm_status": {"used_llm": True, "provider": provider, "error": None},
            }
        # Call failed or wasn't configured — fall back to the template
        # but surface why, rather than pretending it was live-generated.
        return {
            "explanation": template_text,
            "source_snippet": template_source,
            "llm_status": {"used_llm": False, "provider": provider, "error": llm_result["error"]},
        }

    return {
        "explanation": template_text,
        "source_snippet": template_source,
        "llm_status": None,
    }


# Map from the UI language selector value to a plain-ASCII language name
# used inside the LLM prompt.  Non-ASCII language names (e.g. "தமிழ்",
# "తెలుగు") embedded directly in the prompt string can trigger a zero-
# token silent refusal from llama-3.3-70b-versatile on Groq.  Using the
# English name in the instruction keeps the prompt fully ASCII while the
# model still produces output in the correct script.
_LANG_NAME_FOR_PROMPT = {
    "English": "English",
    "हिंदी": "Hindi",
    "ਪੰਜਾਬੀ": "Punjabi",
    "বাংলা": "Bengali",
    "मराठी": "Marathi",
    "ગુજરાતી": "Gujarati",
    "தமிழ்": "Tamil",
    "తెలుగు": "Telugu",
    "ಕನ್ನಡ": "Kannada",
    "മലയാളം": "Malayalam",
    "ଓଡ଼ିଆ": "Odia",
    "অসমীয়া": "Assamese",
    "اردو": "Urdu",
}


def _build_prompt(crop: str, analysis: dict, lang: str, source_snippet: str) -> str:
    """Shared prompt builder for both providers, so Groq and Anthropic
    are grounded in exactly the same instructions and facts.

    Two encoding rules keep the prompt safe for all models:
    1. Language name in the instruction uses the ASCII English name (via
       _LANG_NAME_FOR_PROMPT) — non-ASCII script names in the instruction
       line can trigger a zero-token silent refusal on Groq.
    2. Rupee amounts use "Rs." not "₹" (U+20B9) — the Unicode symbol
       combined with a non-Latin script instruction also causes silent
       refusals on some Groq-hosted models.
    """
    lang_name = _LANG_NAME_FOR_PROMPT.get(lang, "English")
    decision = "WAIT" if analysis["should_wait"] else "SELL NOW"
    prompt = (
        f"You are a plain-spoken farm advisory assistant writing for a smallholder Indian "
        f"farmer with no financial background. Write in {lang_name} only (use the correct "
        f"script for that language), 2-3 short sentences, no markdown, no headers.\n\n"
        f"The decision has ALREADY been calculated as: {decision}. Do not recalculate or "
        f"second-guess it — your only job is to explain it in plain language.\n\n"
        f"Crop: {crop}\n"
        f"Today's price: Rs.{analysis['today_price']}/quintal\n"
        f"{analysis.get('window_days', 90)}-day average price: Rs.{analysis['avg_price']}/quintal\n"
        f"Price percentile within that window: {analysis.get('percentile_rank', '?')} "
        f"(0=lowest seen, 100=highest seen)\n"
        f"Price vs average: {analysis['pct_vs_avg']}%\n"
    )
    if analysis["should_wait"]:
        prompt += (
            f"Suggested wait: {analysis['suggested_days']} days\n"
            f"Projected price after waiting: Rs.{analysis['projected_price']}/quintal\n"
            f"Estimated storage cost: Rs.{analysis['storage_cost']}\n"
            f"Potential gain: Rs.{analysis['potential_gain']}\n"
            f"Net benefit of waiting: Rs.{analysis['net_benefit']}\n"
        )
    prompt += (
        f"\nContext facts (use ONLY these for any storage/seasonal claims, do not invent): "
        f"{source_snippet}\n\n"
        f"Write only the plain explanation text — nothing else."
    )
    return prompt


def generate_with_llm(crop: str, analysis: dict, lang: str, provider: str, api_key: str) -> dict:
    """Real LLM call — routes to Groq or Anthropic depending on
    `provider`, both grounded in the same retrieved facts so the
    "Source" box stays meaningful whichever one is used.

    Returns {"explanation": str, "source_snippet": str, "used_llm": bool,
    "error": str|None}. On any failure (bad key, no internet, rate
    limit, package missing) this returns used_llm=False with the error
    message rather than raising, so the caller can fall back to the
    template cleanly and tell the person what happened instead of
    crashing the page.
    """
    facts = retrieve(crop)
    storage_fact = facts.get("storage", "")
    seasonal_fact = facts.get("seasonal", "")
    source_snippet = f"{storage_fact} {seasonal_fact}".strip()

    if not api_key:
        provider_name = "Groq" if provider == "groq" else "Anthropic"
        return {"explanation": None, "source_snippet": source_snippet,
                "used_llm": False, "error": f"No {provider_name} API key provided."}

    prompt = _build_prompt(crop, analysis, lang, source_snippet)

    if provider == "groq":
        return _call_groq(prompt, api_key, source_snippet)
    return _call_anthropic(prompt, api_key, source_snippet)


def _call_groq(prompt: str, api_key: str, source_snippet: str) -> dict:
    """Groq's API is OpenAI-compatible, so this is a plain REST call
    via `requests` (already a dependency — no extra package needed).
    Model: openai/gpt-oss-120b — the general-purpose chat model available
    on this Groq account. If this ever errors with "model_not_found",
    run:  python -c "import requests; r=requests.get('https://api.groq.com/openai/v1/models',
    headers={'Authorization':'Bearer YOUR_KEY'}); [print(m['id']) for m in r.json()['data']]"
    to list available models and update GROQ_MODEL below.
    """
    import requests

    GROQ_MODEL = "openai/gpt-oss-120b"
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 300,
                "temperature": 0.4,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        finish_reason = choice.get("finish_reason", "unknown")
        # content can be None when the model returns a tool-call or when
        # it soft-refuses — guard before calling .strip().
        raw = choice["message"].get("content") or ""
        text = raw.strip()
        if not text:
            raise ValueError(
                f"Empty response from model (finish_reason={finish_reason!r}). "
                f"Full response: {data}"
            )
        return {"explanation": text, "source_snippet": source_snippet, "used_llm": True, "error": None}
    except requests.HTTPError as e:
        detail = ""
        try:
            detail = e.response.json().get("error", {}).get("message", "")
        except Exception:
            pass
        return {"explanation": None, "source_snippet": source_snippet, "used_llm": False,
                "error": f"Groq API error: {detail or e}"}
    except Exception as e:
        return {"explanation": None, "source_snippet": source_snippet, "used_llm": False,
                "error": f"{type(e).__name__}: {e}"}


def _call_anthropic(prompt: str, api_key: str, source_snippet: str) -> dict:
    """Optional second provider — Claude, via the official SDK. Only
    used if the person picks "Anthropic" in the app and has the
    `anthropic` package installed; Groq (via plain `requests`, no
    extra install) is the default per how this app is meant to run.
    """
    try:
        import anthropic
    except ImportError:
        return {"explanation": None, "source_snippet": source_snippet, "used_llm": False,
                "error": "The 'anthropic' package isn't installed — run: pip install anthropic"}

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model="claude-sonnet-5",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in response.content if hasattr(block, "text")).strip()
        if not text:
            raise ValueError("Empty response from model")
        return {"explanation": text, "source_snippet": source_snippet, "used_llm": True, "error": None}
    except Exception as e:
        return {"explanation": None, "source_snippet": source_snippet, "used_llm": False,
                "error": f"{type(e).__name__}: {e}"}
