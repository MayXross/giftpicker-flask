from flask import Flask, render_template, request, jsonify, session
from dotenv import load_dotenv
import anthropic
import os
import json
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

LANGUAGES = [
    "English", "Slovak", "Czech", "German", "Spanish", "French",
    "Italian", "Portuguese", "Polish", "Hungarian", "Romanian",
    "Japanese", "Chinese", "Korean", "Arabic"
]

CATEGORIES = [
    "Any category", "🎮 Electronics & Gaming", "👗 Fashion & Accessories",
    "🏠 Home & Decor", "📚 Books & Stationery", "🌿 Wellness & Beauty",
    "🍫 Food & Drinks", "🎨 Art & Crafts", "🏋️ Sports & Outdoors",
    "🧸 Toys & Games", "✈️ Travel & Experiences", "🎵 Music & Entertainment", "🐾 Pets"
]

OCCASIONS = [
    "Just a gift", "🎂 Birthday", "🎄 Christmas", "💝 Valentine's Day",
    "👩 Mother's Day", "👨 Father's Day", "🎓 Graduation",
    "💍 Wedding / Anniversary", "🏠 Housewarming", "👶 Baby Shower",
    "🎊 Retirement", "🤒 Get Well Soon", "🙏 Thank You", "✏️ Other..."
]

def check_rate_limit():
    now = datetime.now()
    if 'request_count' not in session:
        session['request_count'] = 0
        session['reset_time'] = (now + timedelta(hours=1)).isoformat()
    
    reset_time = datetime.fromisoformat(session['reset_time'])
    if now > reset_time:
        session['request_count'] = 0
        session['reset_time'] = (now + timedelta(hours=1)).isoformat()
    
    if session['request_count'] >= 10:
        return False
    return True

@app.route('/')
def index():
    if 'request_count' not in session:
        session['request_count'] = 0
        session['reset_time'] = (datetime.now() + timedelta(hours=1)).isoformat()
    
    remaining = max(0, 10 - session.get('request_count', 0))
    return render_template('index.html', 
                         languages=LANGUAGES,
                         categories=CATEGORIES,
                         occasions=OCCASIONS,
                         remaining=remaining)

@app.route('/generate', methods=['POST'])
def generate():
    if not check_rate_limit():
        return jsonify({'error': 'Hourly limit reached. Please try again later.'}), 429
    
    data = request.json
    recipient = data.get('recipient', '')
    interests = data.get('interests', '')
    budget = data.get('budget', 'Under $50')
    language = data.get('language', 'English')
    category = data.get('category', 'Any category')
    occasion = data.get('occasion', 'Just a gift')
    gift_count = int(data.get('gift_count', 5))
    custom_occasion = data.get('custom_occasion', '')
    
    if not recipient or not interests:
        return jsonify({'error': 'Please fill in all fields!'}), 400
    
    if occasion == '✏️ Other...' and custom_occasion:
        occasion = custom_occasion
    
    category_text = f" in the category: {category}" if category != "Any category" else ""
    occasion_text = f" for the occasion: {occasion}" if occasion != "Just a gift" else ""
    
    try:
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2500,
            system=f"""You are an expert gift advisor.
            Always respond in {language}.
            Suggest exactly {gift_count} unique personalized gifts{category_text}{occasion_text}.
            Also generate a short heartfelt dedication message for this occasion.
            Respond ONLY in this exact JSON format, nothing else:
            {{
              "dedication": "A short heartfelt 1-2 sentence dedication message",
              "gifts": [
                {{
                  "name": "Product Name",
                  "reason": "Why perfect in one sentence",
                  "price": "$20-30",
                  "amazon_search": "exact search term",
                  "emoji": "one relevant emoji",
                  "category": "product category"
                }}
              ]
            }}
            Be SPECIFIC. ONLY valid JSON, no extra text.""",
            messages=[{
                "role": "user",
                "content": f"Find {gift_count} gifts for: {recipient}, interests: {interests}, budget: {budget}{category_text}{occasion_text}"
            }]
        )
        
        raw = message.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        result = json.loads(raw)
        gifts = result.get("gifts", [])
        dedication = result.get("dedication", "")
        
        session['request_count'] = session.get('request_count', 0) + 1
        
        affiliate = "giftpickera00-20"
        ebay_campaign = "5339153077"
        ebay_publisher = "7298517"
        
        for gift in gifts:
            search = gift['amazon_search'].replace(' ', '+')
            gift['amazon_url'] = f"https://amazon.com/s?k={search}&tag={affiliate}&language=en_US"
            gift['ebay_url'] = f"https://www.ebay.com/sch/i.html?_nkw={search}&mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={ebay_campaign}&customid=&toolid=10001&mkevt=1&pub={ebay_publisher}"
        
        return jsonify({
            'gifts': gifts,
            'dedication': dedication,
            'remaining': max(0, 10 - session['request_count'])
        })
        
    except Exception as e:
        return jsonify({'error': f'Something went wrong: {str(e)}'}), 500

@app.route('/alternatives', methods=['POST'])
def get_alternatives():
    data = request.json
    gift_name = data.get('gift_name', '')
    recipient = data.get('recipient', '')
    budget = data.get('budget', '')
    language = data.get('language', 'English')
    existing_gifts = data.get('existing_gifts', [])
    
    try:
        alt_msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            system=f"""Gift advisor. Respond in {language}.
            Return 3 alternatives as JSON array:
            [{{"name":"...","price":"...","amazon_search":"...","reason":"...","emoji":"..."}}]
            ONLY valid JSON, no extra text.""",
            messages=[{
                "role": "user",
                "content": f"3 alternatives to: {gift_name} for: {recipient}, budget: {budget}, NOT these: {existing_gifts}"
            }]
        )
        
        raw = alt_msg.content[0].text.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        
        alts = json.loads(raw)
        
        affiliate = "giftpickera00-20"
        ebay_campaign = "5339153077"
        ebay_publisher = "7298517"
        
        for alt in alts:
            search = alt['amazon_search'].replace(' ', '+')
            alt['amazon_url'] = f"https://amazon.com/s?k={search}&tag={affiliate}&language=en_US"
            alt['ebay_url'] = f"https://www.ebay.com/sch/i.html?_nkw={search}&mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={ebay_campaign}&customid=&toolid=10001&mkevt=1&pub={ebay_publisher}"
        
        return jsonify({'alternatives': alts})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
