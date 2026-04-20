🚀 What is Structranet AI?
Structranet AI is an intelligent assistant that helps network engineers design, simulate, and document network architectures. It combines conversational AI (Gemini) with real‑time network topology generation and integration with GNS3.

This platform is built for network professionals who want to:

Design complex topologies using natural language

Generate network diagrams, configurations, and images

Automate deployment via GNS3

Manage conversations and designs with a clean React frontend and Node.js backend

🛠️ Tech Stack
Layer	Technologies
Frontend	React, Vite, React Router, Clerk (authentication), React Markdown, ImageKit React SDK
Backend	Node.js, Express, MongoDB (Mongoose), ImageKit Node SDK, Clerk Backend SDK
AI Services	Google Gemini API (text + image generation), GNS3 automation (planned)
Styling	CSS Modules, custom animations
📋 Prerequisites
Make sure you have the following installed on your machine:

Node.js (v18 or later)

npm (comes with Node.js)

MongoDB Atlas account (or a local MongoDB instance)

A Clerk account for authentication (get your keys from clerk.com)

An ImageKit account for image uploads and transformations (imagekit.io)

A Google Gemini API key (from Google AI Studio)

🧪 Getting Started (Local Development)
Follow these steps to run Structranet AI on your own machine.

1. Clone the repository
bash
git clone https://github.com/your-username/structranet-ai.git
cd structranet-ai
2. Open two terminals
You will need two terminal windows (or split your terminal) – one for the backend and one for the client.

Terminal 1 – Backend
bash
cd backend
npm install
Terminal 2 – Client
bash
cd client
npm install
⚠️ Important: Do not modify or delete the existing .env files or package.json files unless you know exactly what you are doing. The project already includes the necessary configuration for the test version.

3. Set up environment variables
The project uses .env files in both backend and client folders. The required variables are already listed inside the files. If you need to adjust them, you can replace the placeholder values with your own keys, but for the test version you can keep them as they are.

Backend .env example:

text
MONGO=your_mongodb_uri
CLERK_JWT_KEY=your_jwt_key
IMAGE_KIT_ENDPOINT=your_imagekit_endpoint
IMAGE_KIT_PUBLIC_KEY=your_imagekit_public_key
IMAGE_KIT_PRIVATE_KEY=your_imagekit_private_key
CLIENT_URL=http://localhost:5173
Client .env example:

text
VITE_IMAGE_KIT_ENDPOINT=your_imagekit_endpoint
VITE_IMAGE_KIT_PUBLIC_KEY=your_imagekit_public_key
VITE_GEMINI_PUBLIC_KEY=your_gemini_api_key
VITE_CLERK_PUBLISHABLE_KEY=your_clerk_publishable_key
⚠️ Never commit .env files to version control. They are already in .gitignore.

4. Run the application
Now start both servers.

Terminal 1 – Backend
bash
npm start
The backend server will run on http://localhost:3000.

Terminal 2 – Client
bash
npm run dev
The client development server will start on http://localhost:5173.

Open your browser and visit http://localhost:5173. You should see the Structranet AI homepage.

🧑‍💻 How to Use the Test Version
Sign up / Sign in using Clerk (you can use Google, GitHub, or email).

Create a new chat from the dashboard.

Ask questions about network design, or request a network diagram (e.g., “Draw a simple network with 3 routers and 2 switches”).

Upload images to analyze them together with your questions.

Explore the chat history – all conversations are saved in MongoDB.

🔧 Troubleshooting
“Missing publicKey” error – Ensure your ImageKit public key is correctly set in client/.env.

Clerk authentication fails – Verify that your Clerk publishable key and secret key are correct.

MongoDB connection refused – Check that your IP is whitelisted in MongoDB Atlas and the URI is correct.

“Failed to fetch” – Make sure both backend and client are running and that CLIENT_URL in backend points to http://localhost:5173.

🤝 Contributing
This is a test version. If you encounter bugs or have suggestions, feel free to open an issue or submit a pull request.

📄 License
This project is for educational and evaluation purposes. Not intended for production use without proper security hardening.

🎉 Enjoy!
Now you're ready to explore the power of AI in network design. Have fun with Structranet AI!

Built with ❤️ for network engineers everywhere.