from flask import Flask, render_template, request, jsonify, session, Response, stream_with_context
from dotenv import load_dotenv
import anthropic
import os
import json
from datetime import datetime, timedelta

load_dotenv()

app = Flask(__name__)
app.secret_key = os.urandom(24)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

def check_rate_limit():
    now = datetime.now()
    if 'request_count' not in session:
        session['request_count'] = 0
        session['reset_time'] = (now + timedelta(hours=1)).isoformat()
    reset_time = datetime.fromisoformat(session['reset_time'])
    if now > reset_time:
        session['request_count'] = 0
        session['reset_time'] = (now + timedelta(hours=1)).isoformat()
    return session['request_count'] < 10

@app.route('/')
def index():
    if 'request_count' not in session:
        session['request_count'] = 0
        session['reset_time'] = (datetime.now() + timedelta(hours=1)).isoformat()
    remaining = max(0, 10 - session.get('request_count', 0))
    return render_template('index.html', remaining=remaining)

@app.route('/generate', methods=['POST'])
def generate():
    if not check_rate_limit():
        return jsonify({'error': 'Hourly limit reached. Please try again later.'}), 429

    data = request.json
    recipient = data.get('recipient', '')
    interests = data.get('interests', '')
    relationship = data.get('relationship', '')
    age = data.get('age', '')
    personality = data.get('personality', '')
    budget = data.get('budget', 'Under $50')
    language = data.get('language', 'English')
    category = data.get('category', 'Any category')
    occasion = data.get('occasion', 'Just a gift')
    gift_count = int(data.get('gift_count', 5))
    tone = data.get('tone', 'sweet')

    if not recipient or not interests:
        return jsonify({'error': 'Please fill in all fields!'}), 400

    budget_ranges = {
        "Under $20": "between $5 and $20",
        "Under $50": "between $20 and $50",
        "Under $100": "between $50 and $100",
        "Under $200": "between $100 and $200",
        "Under $500": "between $200 and $500",
        "$500+": "above $500"
    }
    budget_text = budget_ranges.get(budget, budget)

    tone_instructions = {
        'sweet': 'Write a sweet, heartfelt dedication message.',
        'funny': 'Write a funny, lighthearted dedication with humor.',
        'romantic': 'Write a romantic, passionate dedication message.',
        'roast': 'Write a funny roast of the gift recipient - playful teasing, not mean.',
        'none': 'Set dedication to empty string "".'
    }
    tone_text = tone_instructions.get(tone, tone_instructions['sweet'])

    category_text = f" in the category: {category}" if category != "Any category" else ""
    occasion_text = f" for the occasion: {occasion}" if occasion != "Just a gift" else ""
    personality_text = f" Personality traits: {personality}." if personality else ""
    age_text = f" Age: {age}." if age else ""
    relationship_text = f" Relationship: {relationship}." if relationship else ""

    system_prompt = f"""You are an expert gift advisor.
            Always respond in {language}.
            STRICT BUDGET RULE: ALL gifts MUST be priced {budget_text}. No exceptions.
            Suggest exactly {gift_count} unique personalized gifts{category_text}{occasion_text}.
            {personality_text}{age_text}{relationship_text}
            {tone_text}
            Also write a 1-sentence gift profile description of this person based on their traits.
            Respond ONLY in this exact JSON format, nothing else:
            {{
              "dedication": "dedication message or empty string",
              "profile_desc": "One sentence describing this person as a gift recipient",
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
            Be SPECIFIC. ONLY valid JSON, no extra text."""

    user_msg = f"Find {gift_count} gifts for: {recipient}, interests: {interests}, budget: {budget_text}{category_text}{occasion_text}"

    def stream():
        full_text = ""
        try:
            with client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=2500,
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}]
            ) as stream_obj:
                for text_chunk in stream_obj.text_stream:
                    full_text += text_chunk
                    # Count gift objects found so far to estimate progress
                    gifts_found = full_text.count('"name"')
                    progress = min(95, int((gifts_found / gift_count) * 90) + 5)
                    chunk = json.dumps({"type": "progress", "value": progress})
                    yield "data: " + chunk + "\n\n"

            # Parse complete response
            raw = full_text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]

            result = json.loads(raw)
            gifts = result.get("gifts", [])
            dedication = result.get("dedication", "")
            profile_desc = result.get("profile_desc", "")

            session['request_count'] = session.get('request_count', 0) + 1

            affiliate = "giftpickera00-20"
            ebay_campaign = "5339153077"
            ebay_publisher = "7298517"

            for gift in gifts:
                search = gift['amazon_search'].replace(' ', '+')
                gift['amazon_url'] = f"https://amazon.com/s?k={search}&tag={affiliate}&language=en_US"
                gift['ebay_url'] = f"https://www.ebay.com/sch/i.html?_nkw={search}&mkcid=1&mkrid=711-53200-19255-0&siteid=0&campid={ebay_campaign}&customid=&toolid=10001&mkevt=1&pub={ebay_publisher}"

            chunk = json.dumps({"type": "done", "gifts": gifts, "dedication": dedication, "profile_desc": profile_desc, "remaining": max(0, 10 - session['request_count'])})
            yield "data: " + chunk + "\n\n"

        except Exception as e:
            chunk = json.dumps({"type": "error", "message": str(e)})
            yield "data: " + chunk + "\n\n"

    return Response(stream_with_context(stream()), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/alternatives', methods=['POST'])
def get_alternatives():
    data = request.json
    gift_name = data.get('gift_name', '')
    recipient = data.get('recipient', '')
    budget = data.get('budget', '')
    language = data.get('language', 'English')
    existing_gifts = data.get('existing_gifts', [])

    budget_ranges = {
        "Under $20": "between $5 and $20",
        "Under $50": "between $20 and $50",
        "Under $100": "between $50 and $100",
        "Under $200": "between $100 and $200",
        "Under $500": "between $200 and $500",
        "$500+": "above $500"
    }
    budget_text = budget_ranges.get(budget, budget)

    try:
        alt_msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=800,
            system=f"""Gift advisor. Respond in {language}.
            STRICT BUDGET RULE: ALL gifts MUST be priced {budget_text}.
            Return 3 alternatives as JSON array:
            [{{"name":"...","price":"...","amazon_search":"...","reason":"...","emoji":"..."}}]
            ONLY valid JSON, no extra text.""",
            messages=[{
                "role": "user",
                "content": f"3 alternatives to: {gift_name} for: {recipient}, budget: {budget_text}, NOT these: {existing_gifts}"
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
