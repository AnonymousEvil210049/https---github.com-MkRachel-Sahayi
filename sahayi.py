import customtkinter as ctk
import cv2
from PIL import Image, ImageDraw
import google.generativeai as genai
from twilio.rest import Client
import speech_recognition as sr
from gtts import gTTS
import pygame
import threading
import schedule
import time
import sqlite3
import json
from datetime import datetime, timedelta
from flask import Flask, request
import urllib.parse
import os

# --- ⚙️ CONFIGURATION ---
GEMINI_API_KEY = "AIzaSyBKjzjwgGb8-xtBrFkM1NchW5huetoN4AI"
TWILIO_SID = "AC3b65c971e9e1f82331cea1201f39b843"
TWILIO_AUTH_TOKEN = "cd1dc62ce27cd7ff7586d47126c5f0b8"
TWILIO_PHONE = "+18312851572 "
FAMILY_PHONE = "+917736033926"
ASHA_WORKER_PHONE = "+919876543211"
NGROK_URL = "https://undramatically-unfond-ryann.ngrok-free.dev"

genai.configure(api_key=GEMINI_API_KEY)
pygame.mixer.init()

# --- 🗄️ ADVANCED NORMALIZED DATABASE ---
def init_db():
    conn = sqlite3.connect('sahayi.db')
    c = conn.cursor()
    # 1. Profile Data
    c.execute('''CREATE TABLE IF NOT EXISTS user_profile 
                 (id INTEGER PRIMARY KEY, name TEXT, honorific TEXT)''')
    # 2. Composition-First Medicines
    c.execute('''CREATE TABLE IF NOT EXISTS medicines 
                 (id INTEGER PRIMARY KEY, brand_name TEXT, active_ingredients TEXT, 
                  purpose TEXT, total_pills INTEGER, remaining_pills INTEGER)''')
    # 3. Normalized Scheduling
    c.execute('''CREATE TABLE IF NOT EXISTS med_schedules 
                 (id INTEGER PRIMARY KEY, med_id INTEGER, time_str TEXT, 
                  pills_per_dose INTEGER, instructions TEXT, start_date TEXT)''')
    # 4. Tracking & Logs
    c.execute('''CREATE TABLE IF NOT EXISTS doses 
                 (id INTEGER PRIMARY KEY, date TEXT, med_name TEXT, status TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS checkins 
                 (date TEXT, status TEXT, mood TEXT, distress_alert INTEGER)''')
    c.execute('''CREATE TABLE IF NOT EXISTS alerts 
                 (id INTEGER PRIMARY KEY, date TEXT, type TEXT, message TEXT, is_resolved INTEGER DEFAULT 0)''')
    conn.commit()
    conn.close()

init_db()

# --- 🌐 EMBEDDED FLASK SERVER (Webhooks) ---
flask_app = Flask(__name__)

@flask_app.route("/twilio_keypress", methods=['POST'])
def twilio_keypress():
    digits = request.form.get('Digits', '')
    call_type = request.args.get('type', '')
    med_name = urllib.parse.unquote(request.args.get('med', ''))
    
    conn = sqlite3.connect('sahayi.db')
    c = conn.cursor()
    today = datetime.now().strftime("%Y-%m-%d")

    if call_type == 'medicine':
        # Get med_id and dose count
        c.execute("SELECT id FROM medicines WHERE brand_name=?", (med_name,))
        med_id = c.fetchone()[0]
        c.execute("SELECT pills_per_dose FROM med_schedules WHERE med_id=?", (med_id,))
        pills_to_deduct = c.fetchone()[0]

        if digits == '1':
            c.execute("INSERT INTO doses (date, med_name, status) VALUES (?, ?, ?)", (today, med_name, 'taken'))
            c.execute("UPDATE medicines SET remaining_pills = remaining_pills - ? WHERE id = ?", (pills_to_deduct, med_id))
        else:
            c.execute("INSERT INTO doses (date, med_name, status) VALUES (?, ?, ?)", (today, med_name, 'missed'))
            
    elif call_type == 'morning_check':
        mood = "good" if digits == '1' else "low" if digits == '3' else "okay"
        c.execute("INSERT INTO checkins (date, status, mood, distress_alert) VALUES (?, ?, ?, ?)", 
                  (today, 'responded', mood, 1 if mood == 'low' else 0))
    
    conn.commit()
    conn.close()
    return "<Response><Say language='ml-IN'>നന്ദി.</Say></Response>"

def run_flask():
    flask_app.run(port=5000, use_reloader=False)

# --- 🖥️ MAIN DESKTOP APPLICATION ---
class SahayiApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sahayi AI - സഹായി")
        self.geometry("1100x900")
        ctk.set_appearance_mode("dark")
        
        self.honorific = self.check_profile()
        
        if not self.honorific:
            self.show_setup_screen()
        else:
            self.init_main_app()

    # --- 👤 PROFILE SETUP ---
    def check_profile(self):
        conn = sqlite3.connect('sahayi.db')
        c = conn.cursor()
        c.execute("SELECT honorific FROM user_profile LIMIT 1")
        res = c.fetchone()
        conn.close()
        return res[0] if res else None

    def show_setup_screen(self):
        self.setup_frame = ctk.CTkFrame(self)
        self.setup_frame.pack(fill="both", expand=True, padx=50, pady=50)
        
        ctk.CTkLabel(self.setup_frame, text="പ്രൊഫൈൽ സജ്ജമാക്കുക (Setup)", font=("Arial", 36, "bold")).pack(pady=30)
        
        self.name_entry = ctk.CTkEntry(self.setup_frame, placeholder_text="പേര് (Name)", font=("Arial", 24), width=400, height=60)
        self.name_entry.pack(pady=20)
        
        ctk.CTkLabel(self.setup_frame, text="ഞാൻ നിങ്ങളെ എന്ത് വിളിക്കണം?", font=("Arial", 24)).pack(pady=10)
        self.honorific_var = ctk.StringVar(value="അമ്മാ")
        options = ["അമ്മാ", "അച്ചാ", "അപ്പാ", "അമ്മേ", "ചേട്ടാ", "ചേച്ചീ"]
        self.dropdown = ctk.CTkOptionMenu(self.setup_frame, values=options, variable=self.honorific_var, font=("Arial", 24), width=400, height=60)
        self.dropdown.pack(pady=20)
        
        ctk.CTkButton(self.setup_frame, text="തുടങ്ങാം (Start)", font=("Arial", 28, "bold"), height=70, command=self.save_profile).pack(pady=40)

    def save_profile(self):
        conn = sqlite3.connect('sahayi.db')
        c = conn.cursor()
        c.execute("INSERT INTO user_profile (name, honorific) VALUES (?, ?)", (self.name_entry.get(), self.honorific_var.get()))
        conn.commit()
        conn.close()
        
        self.honorific = self.honorific_var.get()
        self.setup_frame.destroy()
        self.init_main_app()

    # --- 📱 MAIN UI ---
    def generate_icon(self, color, text):
        """Generates a dummy large icon so CTkImage requirements are met without local files"""
        img = Image.new('RGB', (100, 100), color=color)
        d = ImageDraw.Draw(img)
        d.text((25, 25), text, fill=(255,255,255)) # Simple fallback visual
        return ctk.CTkImage(light_image=img, dark_image=img, size=(80, 80))

    def init_main_app(self):
        self.tabview = ctk.CTkTabview(self, width=1000, height=850)
        self.tabview.pack(padx=20, pady=20)
        
        self.tab_elderly = self.tabview.add(f"{self.honorific} (Home)")
        self.tab_family = self.tabview.add("Family DB")
        
        self.setup_elderly_ui()
        self.setup_family_ui()
        self.start_background_systems()
        self.speak_ml(f"നമസ്കാരം {self.honorific}, സഹായി സജ്ജമാണ്.")

    def setup_elderly_ui(self):
        self.label = ctk.CTkLabel(self.tab_elderly, text=f"നമസ്കാരം {self.honorific}! എന്ത് വേണം?", font=("Arial", 42, "bold"))
        self.label.pack(pady=30)

        # Big Malayalam Buttons with CTkImage
        btn_font = ("Arial", 32, "bold")
        
        self.btn_voice = ctk.CTkButton(self.tab_elderly, text="  എന്നോട് സംസാരിക്കുക", font=btn_font, height=100, fg_color="#28a745", image=self.generate_icon("#1e7e34", "MIC"), command=self.start_voice_chat)
        self.btn_voice.pack(pady=10, fill="x", padx=40)

        self.btn_scan = ctk.CTkButton(self.tab_elderly, text="  പുതിയ കുറിപ്പടി ചേർക്കുക", font=btn_font, height=100, fg_color="#007bff", image=self.generate_icon("#0056b3", "SCAN"), command=self.scan_prescription)
        self.btn_scan.pack(pady=10, fill="x", padx=40)

        self.btn_ask = ctk.CTkButton(self.tab_elderly, text="  ഈ മരുന്ന് എന്താണ്?", font=btn_font, height=100, fg_color="#17a2b8", image=self.generate_icon("#117a8b", "ASK"), command=self.ask_about_medicine)
        self.btn_ask.pack(pady=10, fill="x", padx=40)

        self.btn_match = ctk.CTkButton(self.tab_elderly, text="  മരുന്ന് ശരിയാണോ എന്ന് നോക്കാം", font=btn_font, height=100, fg_color="#fd7e14", image=self.generate_icon("#e8590c", "MATCH"), command=self.match_medicine_flow)
        self.btn_match.pack(pady=10, fill="x", padx=40)

        self.btn_sos = ctk.CTkButton(self.tab_elderly, text="  അത്യാവശ്യം (SOS)", font=("Arial", 40, "bold"), height=120, fg_color="#dc3545", image=self.generate_icon("#bd2130", "SOS"), 
                                     command=lambda: self.trigger_call(FAMILY_PHONE, f"അടിയന്തരം! {self.honorific}ക്ക് സഹായം ആവശ്യമുണ്ട്."))
        self.btn_sos.pack(pady=20, fill="x", padx=40)

    # --- 🗣️ AUDIO HELPER ---
    def speak_ml(self, text):
        try:
            tts = gTTS(text=text, lang='ml')
            tts.save("temp.mp3")
            pygame.mixer.music.load("temp.mp3")
            pygame.mixer.music.play()
        except Exception as e:
            print("Audio error:", e)

    # --- 🤖 FEATURE 5: ASK ABOUT MEDICINE (Multimodal Image + Audio) ---
    def ask_about_medicine(self):
        self.label.configure(text="മരുന്ന് കാണിക്കുക, എന്നിട്ട് ചോദ്യം ചോദിക്കുക...")
        self.update()
        threading.Thread(target=self._process_ask_medicine).start()

    def _process_ask_medicine(self):
        # 1. Capture Image
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        if not ret: return
        cv2.imwrite("ask_pill.jpg", frame)
        img = Image.open("ask_pill.jpg")

        self.speak_ml(f"{self.honorific}, ചോദ്യം ചോദിച്ചോളൂ.")
        time.sleep(2) # Give time for TTS to finish

        # 2. Capture Audio
        recognizer = sr.Recognizer()
        user_query = "What is this medicine and how to take it?" # Fallback
        with sr.Microphone() as source:
            try:
                audio = recognizer.listen(source, timeout=6)
                user_query = recognizer.recognize_google(audio, language="ml-IN")
            except: pass

        # 3. Multimodal Gemini Call
        model = genai.GenerativeModel('gemini-1.5-pro')
        prompt = f"The user uploaded an image of a medicine and asked in Malayalam: '{user_query}'. Identify the medicine and answer their question clearly and simply in Malayalam."
        
        response = model.generate_content([prompt, img])
        self.speak_ml(response.text)
        self.label.configure(text=f"സഹായി സജ്ജമാണ്.")

    # --- 🧪 FEATURE 6 & 7: PILL VS RX MATCHER (Replacement Reasoning) ---
    def match_medicine_flow(self):
        self.label.configure(text="ആദ്യം കുറിപ്പടി (Prescription) കാണിക്കുക...")
        self.speak_ml(f"{self.honorific}, ആദ്യം ഡോക്ടറുടെ കുറിപ്പടി ക്യാമറയിൽ കാണിക്കുക.")
        self.update()
        threading.Thread(target=self._process_match_flow).start()

    def _process_match_flow(self):
        # Step 1: Capture Rx
        time.sleep(4)
        cap = cv2.VideoCapture(0)
        ret, frame1 = cap.read()
        cv2.imwrite("match_rx.jpg", frame1)
        
        # Step 2: Capture Pill
        self.label.configure(text="ഇനി മരുന്ന് (Pill Strip) കാണിക്കുക...")
        self.speak_ml("ഇനി വാങ്ങിയ മരുന്ന് കാണിക്കുക.")
        time.sleep(4)
        ret, frame2 = cap.read()
        cap.release()
        cv2.imwrite("match_pill.jpg", frame2)

        self.label.configure(text="പരിശോധിക്കുന്നു... (Analyzing...)")
        
        # Step 3: AI Reasoning
        model = genai.GenerativeModel('gemini-1.5-pro')
        rx_img = Image.open("match_rx.jpg")
        pill_img = Image.open("match_pill.jpg")
        
        prompt = """Compare the prescription image and the physical pill strip image. 
        Focus heavily on ACTIVE INGREDIENTS and STRENGTH, not just brand names. 
        Determine if it's the exact same, a generic equivalent, or a mismatch/wrong medicine.
        Return ONLY JSON:
        {"safe_to_take": true/false, "explanation_malayalam": "Simple Malayalam explanation of whether they match, if it's a generic substitute, or if they should consult a doctor."}"""
        
        response = model.generate_content([prompt, rx_img, pill_img])
        try:
            data = json.loads(response.text.replace('```json', '').replace('```', ''))
            self.speak_ml(data["explanation_malayalam"])
            if not data["safe_to_take"]:
                self.trigger_call(FAMILY_PHONE, f"മുന്നറിയിപ്പ്! {self.honorific} വാങ്ങിയ മരുന്നും കുറിപ്പടിയും തമ്മിൽ വ്യത്യാസമുണ്ട്.")
        except:
            self.speak_ml("ക്ഷമിക്കണം, വ്യക്തമായി കാണാൻ കഴിഞ്ഞില്ല.")

    # --- 📋 FEATURE 3 & 4: AUTO REGIMEN FROM RX (Normalized DB) ---
    def scan_prescription(self):
        self.label.configure(text="വായിക്കുന്നു... (Scanning...)")
        self.update()
        
        cap = cv2.VideoCapture(0)
        ret, frame = cap.read()
        cap.release()
        
        if ret:
            cv2.imwrite("rx.jpg", frame)
            threading.Thread(target=self._process_prescription).start()

    def _process_prescription(self):
        model = genai.GenerativeModel('gemini-1.5-pro')
        img = Image.open("rx.jpg")
        today_str = datetime.now().strftime("%Y-%m-%d")
        
        prompt = f"""Extract medicines from this prescription. Assume start date is {today_str}.
        Return ONLY a JSON array. Format:
        [{{
            "brand_name": "Panadol",
            "active_ingredients": "Paracetamol 500mg",
            "purpose": "പനി കുറയ്ക്കാൻ",
            "total_pills_dispensed": 20,
            "schedules": [
                {{"time_str": "09:00", "pills_per_dose": 1, "instructions": "ഭക്ഷണത്തിന് ശേഷം"}},
                {{"time_str": "21:00", "pills_per_dose": 1, "instructions": "ഭക്ഷണത്തിന് ശേഷം"}}
            ]
        }}]"""
        
        response = model.generate_content([prompt, img])
        try:
            medicines = json.loads(response.text.replace('```json', '').replace('```', ''))
            
            conn = sqlite3.connect('sahayi.db')
            c = conn.cursor()
            
            for med in medicines:
                # Insert into main table
                c.execute("INSERT INTO medicines (brand_name, active_ingredients, purpose, total_pills, remaining_pills) VALUES (?, ?, ?, ?, ?)", 
                          (med['brand_name'], med['active_ingredients'], med['purpose'], med['total_pills_dispensed'], med['total_pills_dispensed']))
                med_id = c.lastrowid
                
                # Insert into normalized schedules table
                for sched in med['schedules']:
                    c.execute("INSERT INTO med_schedules (med_id, time_str, pills_per_dose, instructions, start_date) VALUES (?, ?, ?, ?, ?)",
                              (med_id, sched['time_str'], sched['pills_per_dose'], sched['instructions'], today_str))
                    
                    # Add to dynamic background scheduler
                    t_obj = datetime.strptime(sched['time_str'], "%H:%M")
                    pre_time = (t_obj - timedelta(minutes=30)).strftime("%H:%M")
                    
                    schedule.every().day.at(pre_time).do(self.pre_reminder, med['brand_name'])
                    schedule.every().day.at(sched['time_str']).do(self.medicine_routine, med['brand_name'])

            conn.commit()
            conn.close()
            
            self.speak_ml(f"മരുന്നുകൾ ചേർത്തു. സമയം ആകുമ്പോൾ ഞാൻ ഓർമ്മിപ്പിക്കാം.")
            self.label.configure(text="സഹായി സജ്ജമാണ്.")
            self.refresh_dashboard()
        except Exception as e:
            print(e)
            self.speak_ml("വായിക്കാൻ കഴിഞ്ഞില്ല.")

    # --- 🗣️ VOICE CHAT (Unchanged core logic, updated TTS) ---
    def start_voice_chat(self):
        self.label.configure(text="കേൾക്കുന്നുണ്ട്...")
        self.update()
        threading.Thread(target=self._process_voice).start()

    def _process_voice(self):
        recognizer = sr.Recognizer()
        with sr.Microphone() as source:
            try:
                audio = recognizer.listen(source, timeout=5)
                text = recognizer.recognize_google(audio, language="ml-IN")
                
                model = genai.GenerativeModel('gemini-1.5-pro')
                prompt = f"""User ({self.honorific}) said in Malayalam: '{text}'. Respond strictly in JSON:
                {{"reply": "your Malayalam reply addressing them as {self.honorific}", "distress_detected": true/false, "mood": "good/okay/low"}}"""
                
                response = model.generate_content(prompt)
                ai_data = json.loads(response.text.replace('```json', '').replace('```', ''))
                
                self.speak_ml(ai_data['reply'])
                
                if ai_data['distress_detected']:
                    self.trigger_call(FAMILY_PHONE, f"അടിയന്തരം! {self.honorific}യുടെ സംസാരത്തിൽ ബുദ്ധിമുട്ട് തോന്നി.")
                self.label.configure(text="സഹായി സജ്ജമാണ്.")
            except:
                self.label.configure(text="മനസ്സിലായില്ല.")

    # --- ⚙️ BACKGROUND & DASHBOARD (Truncated for brevity, logic remains identical to previous block) ---
    def trigger_call(self, to_phone, message, gather_url=None):
        try:
            client = Client(TWILIO_SID, TWILIO_AUTH_TOKEN)
            twiml = f'<Response><Say language="ml-IN">{message}</Say>'
            if gather_url: twiml += f'<Gather action="{gather_url}" numDigits="1" timeout="10" />'
            twiml += '</Response>'
            client.calls.create(twiml=twiml, to=to_phone, from_=TWILIO_PHONE)
        except: pass

    def pre_reminder(self, med_name):
        self.trigger_call(FAMILY_PHONE, f"{self.honorific}, അര മണിക്കൂറിനുള്ളിൽ {med_name} കഴിക്കണം. വെള്ളം എടുത്തു വെക്കുക.")

    def medicine_routine(self, med_name):
        safe_med = urllib.parse.quote(med_name)
        url = f"{NGROK_URL}/twilio_keypress?type=medicine&med={safe_med}"
        self.trigger_call(FAMILY_PHONE, f"മരുന്ന് കഴിക്കാൻ സമയമായി. {med_name} കഴിച്ച ശേഷം ഫോണിൽ ഒന്ന് അമർത്തുക.", gather_url=url)

    def start_background_systems(self):
        threading.Thread(target=run_flask, daemon=True).start()
        
        # Load existing normalized schedules
        conn = sqlite3.connect('sahayi.db')
        c = conn.cursor()
        c.execute('''SELECT medicines.brand_name, med_schedules.time_str 
                     FROM medicines JOIN med_schedules ON medicines.id = med_schedules.med_id''')
        for row in c.fetchall():
            t_obj = datetime.strptime(row[1], "%H:%M")
            schedule.every().day.at((t_obj - timedelta(minutes=30)).strftime("%H:%M")).do(self.pre_reminder, row[0])
            schedule.every().day.at(row[1]).do(self.medicine_routine, row[0])
        conn.close()

        threading.Thread(target=self._run_scheduler, daemon=True).start()

    def _run_scheduler(self):
        while True:
            schedule.run_pending()
            time.sleep(1)

    def setup_family_ui(self):
        # UI Setup for Dashboard (Similar to previous implementation)
        ctk.CTkLabel(self.tab_family, text="Family Dashboard", font=("Arial", 24)).pack()
        self.db_display = ctk.CTkTextbox(self.tab_family, width=900, height=600, font=("Arial", 16))
        self.db_display.pack()
        ctk.CTkButton(self.tab_family, text="Refresh Data", command=self.refresh_dashboard).pack(pady=10)

    def refresh_dashboard(self):
        self.db_display.delete("1.0", "end")
        conn = sqlite3.connect('sahayi.db')
        c = conn.cursor()
        
        self.db_display.insert("end", "📊 --- NORMALIZED PILL INVENTORY ---\n")
        c.execute('''SELECT m.brand_name, m.active_ingredients, m.remaining_pills, s.time_str, s.pills_per_dose 
                     FROM medicines m JOIN med_schedules s ON m.id = s.med_id''')
        for row in c.fetchall():
            self.db_display.insert("end", f"💊 {row[0]} ({row[1]}) | Time: {row[3]} | Dose: {row[4]} | Total Left: {row[2]}\n")
            
        conn.close()

if __name__ == "__main__":
    app = SahayiApp()
    app.mainloop()