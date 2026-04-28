# 🚀 Structranet AI

## 📌 Overview

**Structranet AI** is an intelligent assistant designed to help network engineers **design, simulate, and document network architectures efficiently**.

It combines **conversational AI (Google Gemini)** with **real-time network topology generation** and planned integration with **GNS3 automation**, creating a powerful all-in-one platform for modern network design.

---

## 🎯 Key Capabilities

Structranet AI is built for network professionals who want to:

* 🧠 Design complex network topologies using **natural language**
* 📊 Generate **network diagrams, configurations, and images**
* ⚙️ Automate deployment through **GNS3 integration** *(planned)*
* 💬 Manage conversations and designs via a **modern web interface**

---

## 🛠️ Tech Stack

| Layer           | Technologies                                                                          |
| --------------- | ------------------------------------------------------------------------------------- |
| **Frontend**    | React, Vite, React Router, Clerk (Authentication), React Markdown, ImageKit React SDK |
| **Backend**     | Node.js, Express, MongoDB (Mongoose), ImageKit Node SDK, Clerk Backend SDK            |
| **AI Services** | Google Gemini API (text + image generation), GNS3 Automation *(planned)*              |
| **Styling**     | CSS Modules, Custom Animations                                                        |

---

## 📋 Prerequisites

Make sure you have the following installed:

* Node.js (v18 or later)
* npm (comes with Node.js)
* MongoDB Atlas account (or local MongoDB)
* Clerk account (authentication keys from [https://clerk.com](https://clerk.com))
* ImageKit account ([https://imagekit.io](https://imagekit.io))
* Google Gemini API key (Google AI Studio)

---

## 🧪 Getting Started (Local Development)

### 1. Clone the Repository

```bash
git clone https://github.com/S-Eldeen/StructuraNet-AI.git
cd structranet-ai
```

---

### 2. Open Two Terminals

You will need two terminal windows:

* **Terminal 1:** Backend
* **Terminal 2:** Client

---

### 3. Install Dependencies

**Backend**

```bash
cd backend
npm install
```

**Client**

```bash
cd client
npm install
```

---

## ⚠️ Important Notes

* Do **not modify or delete** existing `.env` or `package.json` files unless necessary
* The project already includes working configurations for testing

---

## 🔐 Environment Variables

Both `backend` and `client` folders include `.env` files.

### Backend `.env`

```env
MONGO=your_mongodb_uri
CLERK_JWT_KEY=your_jwt_key
IMAGE_KIT_ENDPOINT=your_imagekit_endpoint
IMAGE_KIT_PUBLIC_KEY=your_imagekit_public_key
IMAGE_KIT_PRIVATE_KEY=your_imagekit_private_key
CLIENT_URL=http://localhost:5173
```

### Client `.env`

```env
VITE_IMAGE_KIT_ENDPOINT=your_imagekit_endpoint
VITE_IMAGE_KIT_PUBLIC_KEY=your_imagekit_public_key
VITE_GEMINI_PUBLIC_KEY=your_gemini_api_key
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
```

⚠️ **Never commit `.env` files** — they are already included in `.gitignore`.

---

## ▶️ Running the Application

**Start Backend**

```bash
npm start
```

Runs on: **[http://localhost:3000](http://localhost:3000)**

**Start Client**

```bash
npm run dev
```

Runs on: **[http://localhost:5173](http://localhost:5173)**

---

## 🌐 Access the App

Open your browser and visit:

```
http://localhost:5173
```

---

## 🧑‍💻 How to Use (Test Version)

1. Sign up / Sign in via **Clerk** (Google, GitHub, or email)

2. Create a new chat from the dashboard

3. Ask questions or request network designs

   **Example:**

   ```
   Draw a simple network with 3 routers and 2 switches
   ```

4. Upload images for analysis

5. View saved conversations (stored in MongoDB)

---

## 🔧 Troubleshooting

| Issue                      | Solution                                                    |
| -------------------------- | ----------------------------------------------------------- |
| Missing publicKey          | Check ImageKit public key in `client/.env`                  |
| Clerk authentication fails | Verify Clerk keys                                           |
| MongoDB connection refused | Whitelist your IP & verify URI                              |
| Failed to fetch            | Ensure both servers are running and `CLIENT_URL` is correct |

---

## 🤝 Contributing

This is a **test version**. Contributions are welcome:

* Open issues
* Submit pull requests
* Suggest improvements

---

Here’s a clean, professional **License section** you can drop directly into your README:

---

## 📄 License

This project is developed as part of a **Graduation Project (2026)** at:

**Faculty of Engineering, Tanta University**
**Computer and Automatic Control Department**

### 🔖 License Name: **E-TU License (Educational – Tanta University)**

This software is provided for **educational and evaluation purposes only**.

### 📌 Terms of Use

* ✅ Free to use for **learning, research, and academic purposes**
* ❌ Not permitted for **commercial use**
* ❌ Redistribution or modification for production use is **not allowed without permission**
* ⚠️ No warranty or guarantee is provided with this software

### 👨‍🎓 Academic Attribution

Any use of this project must include proper acknowledgment of:

> *Structranet AI — Graduation Project (2026), Faculty of Engineering, Tanta University*

---

## 🎉 Final Note

You're now ready to explore the power of **AI-driven network design**.

**Structranet AI** — built with ❤️ for network engineers everywhere.
