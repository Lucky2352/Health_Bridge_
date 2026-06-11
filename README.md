# 🏥 HealthBridge  
### NAMASTE + ICD-11 Electronic Medical Records (EMR) System

![SIH](https://img.shields.io/badge/Built%20at-SIH-orange)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-Web%20Framework-black)
![FHIR](https://img.shields.io/badge/FHIR-R4-green)
![Database](https://img.shields.io/badge/Database-SQLite-lightgrey)
![License](https://img.shields.io/badge/License-MIT-brightgreen)

> **HealthBridge** is a next-generation Electronic Medical Records (EMR) system that **bridges traditional Indian AYUSH medicine (NAMASTE codes)** with **global healthcare standards (ICD-11 & FHIR R4)**, enabling true interoperability between ancient medical knowledge and modern clinical systems.

> 🚀 Developed by **Team `Name_Space`** during **Smart India Hackathon (SIH)** to bridge AYUSH and global healthcare standards.

---

## 🌍 Project Motivation

Healthcare systems often operate in silos:

- Traditional AYUSH practices lack global interoperability  
- Modern EMRs ignore indigenous medical coding  
- Patient-doctor relationships are poorly tracked  
- Interoperability with national and international standards is limited  

**HealthBridge solves this** by unifying:
- 🇮🇳 **NAMASTE (AYUSH) codes**
- 🌐 **ICD-11 (WHO standard)**
- 🔁 **FHIR R4 interoperability**
- 🆔 **ABHA ID integration**

---

## 🏆 Hackathon Details

**Built during:** Smart India Hackathon (SIH)  
**Team Name:** `Name_Space`  
**Problem Statement:** Develop API code to integrate NAMASTE and/or ICD-11 TM2 into EMR systems (EHR STANDARDS- INDIA )

**Problem Theme:** MedTech / BioTech / HealthTech

**Development Type:** Hackathon Prototype (Scalable Architecture)

HealthBridge was conceptualized and developed as part of the **Smart India Hackathon (SIH)**, focusing on solving real-world healthcare interoperability challenges by bridging **traditional AYUSH medical systems** with **global ICD-11 and FHIR R4 standards**.

The project emphasizes:
- Rapid yet scalable system design
- Standards-compliant healthcare interoperability
- Practical implementation for Indian healthcare infrastructure

## ✨ Key Features

### 🔐 Authentication & Access Control
- Role-based access (**Doctor / Patient / Admin**)
- Secure login & signup system
- Google OAuth2 support *(optional)*
- Flask-Login session handling
- JWT authentication for APIs

### 🆔 Unique Identification System
- Auto-generated **Patient IDs** (`P0001`, `P0002`, …)
- Auto-generated **Doctor IDs** (`D0001`, `D0002`, …)
- **ABHA ID** validation & linking (India-specific)

### 🧬 Medical Code Management
- 🪔 **NAMASTE codes** (Ayurveda, Unani, Siddha, Homeopathy)
- 🧾 **ICD-11 integration** (WHO)
- 🔄 Bidirectional code translation
- ⚡ Real-time medical code search
- 📄 CSV fallback when APIs are unavailable

### 👤 Patient Management
- Complete demographic profiles
- Longitudinal medical history
- Diagnosis tracking with doctor attribution
- Prescription management
- Appointment scheduling
- ABHA-linked patient profiles

### 🩺 Doctor Portal
- Professional dashboard with analytics
- Patient diagnosis entry
- Code search & translation
- Doctor-patient relationship tracking
- Reports & insights

### 🧍 Patient Portal
- Personal health dashboard
- View diagnoses & prescriptions
- Appointment management
- Profile & ABHA ID linking
- Transparency with doctor details

### 🔁 FHIR R4 Interoperability
- Full FHIR Bundle upload & validation
- FHIR Resources:
  - Patient
  - Condition
  - Observation
- CodeSystem & ValueSet support
- ConceptMap for NAMASTE ↔ ICD-11
- FHIR export for external systems

### 📊 Analytics & Reporting
- Real-time statistics dashboards
- PDF & Excel report exports
- Interactive charts & visualizations
- Pandas-powered data processing

### 🎨 UI / UX Design
- Futuristic **aqua-themed** interface
- Glossy card-based layouts
- Fully responsive (mobile-friendly)
- Unified design for doctors & patients
- Professional sidebar navigation

---

## 🖼 Screenshots

> _Screenshots will be added here_
- Doctor Dashboard  
- Patient Portal  
- Diagnosis Entry  
- NAMASTE ↔ ICD-11 Search  
- FHIR Upload  

---

## 🧰 Tech Stack

| Layer | Technology |
|-----|-----------|
| Backend | Python, Flask |
| Auth | Flask-Login, JWT |
| Database | SQLite |
| Frontend | HTML5, CSS3, JavaScript (ES6+) |
| Interoperability | FHIR R4 |
| APIs | WHO ICD-11 API |
| Analytics | Pandas |
| Security | Werkzeug password hashing |

---

## 🚀 Installation

### 1️⃣ Clone the Repository
```bash
git clone https://github.com/yourusername/HealthBridge.git
cd HealthBridge
```

### 2️⃣ Create Virtual Environment
```
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
```

### 3️⃣ Install Dependencies
```
pip install -r requirements.txt
```

## ⚙️ Configuration
Create a .env file in the root directory:
```
SECRET_KEY=your_secret_key
JWT_SECRET_KEY=your_jwt_secret
ICD11_CLIENT_ID=your_who_client_id
ICD11_CLIENT_SECRET=your_who_client_secret
FLASK_ENV=development
```
🔑 ICD-11 API Credentials:
Get them from 👉 [https://icd.who.int/icdapi](https://icd.who.int/icdapi)

## ▶️ Running the Application
```
python app.py
```
Access the app at:
```
http://127.0.0.1:5000
```

## 🧭 Key Routes

| Route                 | Description                      |
| --------------------- | -------------------------------- |
| `/enhanced/login`     | User login                       |
| `/enhanced/signup`    | User registration                |
| `/enhanced/dashboard` | Role-based dashboard             |
| `/patients/`          | Patient management (Doctor only) |
| `/diagnosis`          | Save diagnosis                   |
| `/search`             | NAMASTE + ICD-11 search          |
| `/translate_code`     | Code translation                 |
| `/fhir/`              | FHIR interoperability            |
| `/reports/`           | Analytics dashboard              |
| `/patient/records`    | Patient medical records          |
| `/patient/profile`    | Profile & ABHA ID                |

## 🗄 Database Schema (Simplified)
```
enhanced_auth.db
```
### Users
- id
- role
- patient_id
- doctor_id
- email
- password_hash

### Core Tables
- Diagnoses → doctor_id ↔ patient_id ↔ codes
- Prescriptions → medications
- Appointments → scheduling
- Reports → analytics & documents

All tables use foreign key constraints.

## 🔒 Security Features
- No hardcoded credentials
- Environment-based secrets
- Secure password hashing
- Role-based access control
- Input validation
- ABHA ID formatting & validation
- Database referential integrity

## 🤝 Contributing
Contributions are welcome!
1. Fork the repository
2. Create a feature branch
3. Commit changes with clear messages
4. Open a Pull Request

Please follow clean code and documentation standards.

## 📄 License
This project is licensed under the MIT License.
See LICENSE file for details.

## 🙏 Acknowledgments
- **Smart India Hackathon (SIH)** – for providing the platform to solve national-scale problems
- **Team `namespace`** – for collaborative design, development, and innovation
- **WHO ICD-11 API** – for global disease classification standards
- **FHIR R4 Community** – for interoperability guidelines
- **AYUSH / NAMASTE Framework** – for traditional Indian medical coding
- Open-source contributors and healthcare technologists

## Contact & Support
Maintainer: Aaditya Siddharth Bansod

📧 Email: aadityasbansod@gmail.com

🔗 LinkedIn: [https://linkedin.com/in/yourprofile](https://www.linkedin.com/in/aaditya-siddharth-bansod-889590333/)

HealthBridge aims to modernize healthcare while respecting traditional medical systems.
