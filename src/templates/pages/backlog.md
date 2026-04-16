# 🚀 Project Backlog

A living list of projects in progress, ideas in development, and experiments under construction.  

---

## 🧾 Recipes
**Description:**  
An app for managing purchases by uploading receipts and in-store price tags. You can then *chat with your purchases* to answer questions like:  
- *“How much have I spent on groceries this month?”*  
- *“Where did I see that sale on ground beef?”*  

Currently reworking the vector embedding workflow for better retrieval quality.  

**Progress:** ▓▓▓▓▓▓▓▓░░ (80%)

---

## 📧 Propel Mail RAG Reply
**Description:**  
An automated inbox assistant for Propel’s **info@** address that responds to common parent questions like:  
- *“My son is 8, do you have a team for his age?”*  
- *“Where and when do you meet for practice?”*  
- *“How much does it cost to join?”*  
- *“What comes with my daughter’s membership?”*  

**Architecture Components:**  
1. ⏰ **Cron job** – triggers a script on schedule  
2. 📥 **Inbox reader script** – fetches new messages and queries the RAG API  
3. 🧠 **RAG API** – handles data ingestion and retrieval  
4. 🗄️ **PostgreSQL database** – purpose-built FAQ schema storing embeddings, documents, and metadata  

**Current Focus:**  
- Register the app with Google  
- Create SQL schema  
- Write ingestion logic (possibly agentic)  
- Implement retrieval logic (likely agentic)  
- Test all components together  

**Progress:** ▓░░░░░░░░░ (15%)

---

## ⌚ Pixel Watch Face
**Description:**  
A fully custom Google Pixel Watch face with perfect daily utility:  
- Time + readable date  
- Steps & heart rate  
- Google Calendar  
- Outlook Calendar  

**Progress:** ░░░░░░░░░░ (Not Started)

---

## 📬 SparkMail
**Description:**  
A self-hosted mail server to:  
- Ingest emailed receipts (e.g. Amazon) for the **Recipes** app  
- Provide messaging for threat detection alerts and other systems  

Currently stuck on inbound email due to ISP-blocked ports. Experimenting with Cloudflare DNS, Mailgun, and Traefik to resolve.  

**Progress:** ▓▓▓▓▓▓▓░░░ (70%)

---

## 🥽 HUD
**Description:**  
A fun family project: building a heads-up display with off-the-shelf hardware (Raspberry Pi, portable battery, 3D-printed housing). Designed for text notifications, simple graphics, and voice/BT integration.  

**Progress:** ░░░░░░░░░░ (Not Started)

---

## 🛡️ Threat Detection
**Description:**  
A home network monitoring system using:  
- A managed switch  
- Server with a NIC in promiscuous mode  
- API integrations + custom analysis code  

Goal: detect suspicious traffic and generate actionable alerts.  

**Progress:** ░░░░░░░░░░ (Not Started)

---
