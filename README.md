🚀 Structranet AI
What is Structranet AI?
Structranet AI is an intelligent assistant designed to help network engineers design, simulate, and document network architectures efficiently.
It combines conversational AI (Google Gemini) with real-time network topology generation and planned integration with GNS3 automation, creating a powerful all-in-one platform for modern network design.

🎯 Key Capabilities
Structranet AI is built for network professionals who want to:


Design complex network topologies using natural language


Generate network diagrams, configurations, and images


Automate deployment through GNS3 integration (planned)


Manage conversations and designs via a modern web interface



🛠️ Tech Stack
LayerTechnologiesFrontendReact, Vite, React Router, Clerk (Authentication), React Markdown, ImageKit React SDKBackendNode.js, Express, MongoDB (Mongoose), ImageKit Node SDK, Clerk Backend SDKAI ServicesGoogle Gemini API (text + image generation), GNS3 Automation (planned)StylingCSS Modules, Custom Animations

📋 Prerequisites
Ensure you have the following installed:


Node.js (v18 or later)


npm (included with Node.js)


MongoDB Atlas account (or local MongoDB)


Clerk account (authentication keys from clerk.com)


ImageKit account (imagekit.io)


Google Gemini API key (Google AI Studio)



🧪 Getting Started (Local Development)
1. Clone the Repository
git clone https://github.com:S-Eldeen/AutoTopology.git
cd structranet-ai

3. Open Two Terminals
You’ll need:


One for the backend


One for the client



3. Install Dependencies
Terminal 1 – Backend
cd backendnpm install
Terminal 2 – Client
cd clientnpm install

⚠️ Important Notes


Do not modify or delete existing .env or package.json files unless necessary


The project already includes working configurations for testing



🔐 Environment Variables
Both backend and client folders include .env files.
Backend .env
MONGO=your_mongodb_uriCLERK_JWT_KEY=your_jwt_keyIMAGE_KIT_ENDPOINT=your_imagekit_endpointIMAGE_KIT_PUBLIC_KEY=your_imagekit_public_keyIMAGE_KIT_PRIVATE_KEY=your_imagekit_private_keyCLIENT_URL=http://localhost:5173
Client .env
VITE_IMAGE_KIT_ENDPOINT=your_imagekit_endpointVITE_IMAGE_KIT_PUBLIC_KEY=your_imagekit_public_keyVITE_GEMINI_PUBLIC_KEY=your_gemini_api_keyVITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
⚠️ Never commit .env files — they are already included in .gitignore.

▶️ Running the Application
Start Backend
npm start
Runs on: http://localhost:3000
Start Client
npm run dev
Runs on: http://localhost:5173

🌐 Access the App
Open your browser and go to:
http://localhost:5173

🧑‍💻 How to Use (Test Version)


Sign up / Sign in via Clerk (Google, GitHub, or email)


Create a new chat from the dashboard


Ask questions or request network designs
Example:
“Draw a simple network with 3 routers and 2 switches”


Upload images for analysis


View saved conversations (stored in MongoDB)



🔧 Troubleshooting
IssueSolutionMissing publicKeyCheck ImageKit public key in client/.envClerk authentication failsVerify Clerk keysMongoDB connection refusedWhitelist IP & verify URIFailed to fetchEnsure both servers are running and CLIENT_URL is correct

🤝 Contributing
This is a test version.
Feel free to:


Open issues


Submit pull requests


Suggest improvements



📄 License
This project is intended for educational and evaluation purposes only.
Not recommended for production without proper security hardening.

🎉 Final Note
You're now ready to explore the power of AI-driven network design.
Structranet AI — built with ❤️ for network engineers everywhere.
