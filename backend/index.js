import express from "express";
import dotenv from "dotenv";
import cors from "cors";
import mongoose from "mongoose";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";
import { spawn } from "child_process";
import path from "path";
import fs from "fs";
import multer from "multer";
import { fileURLToPath } from "url";

import User from "./models/User.js";
import UserChat from "./models/userChat.js";
import Chat from "./models/chat.js";

import dns from "dns";
dns.setServers(["1.1.1.1", "8.8.8.8"]);

dotenv.config();

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const port = process.env.PORT || 3000;
const app = express();

app.use(
  cors({
    origin: (origin, callback) => {
      if (!origin) return callback(null, true);
      if (origin.startsWith("http://localhost:")) {
        return callback(null, true);
      }
      callback(new Error("Not allowed by CORS"));
    },
    credentials: true,
  })
);
app.use(express.json({ limit: "25mb" }));
app.use(express.urlencoded({ extended: true, limit: "25mb" }));

const connect = async () => {
  try {
    await mongoose.connect(process.env.MONGO);
    console.log("✅ Connected to MongoDB");
  } catch (error) {
    console.error("❌ MongoDB connection error:", error.message);
    process.exit(1);
  }
};

/* ================= AUTH ================= */

app.post("/api/auth/signup", async (req, res) => {
  try {
    const { username, email, password } = req.body;
    const existingUser = await User.findOne({ email });
    if (existingUser) {
      return res.status(400).json({ error: "Email already exists" });
    }
    const hashedPassword = await bcrypt.hash(password, 10);
    await User.create({ username, email, password: hashedPassword });
    res.status(201).json({ message: "User created successfully" });
  } catch (err) {
    console.error("Signup error:", err);
    res.status(500).json({ error: "Signup failed" });
  }
});

app.post("/api/auth/signin", async (req, res) => {
  try {
    const { email, password } = req.body;
    const user = await User.findOne({ email });
    if (!user) return res.status(400).json({ error: "Invalid credentials" });
    const isMatch = await bcrypt.compare(password, user.password);
    if (!isMatch) return res.status(400).json({ error: "Invalid credentials" });
    const userId = user._id.toString();
    const token = jwt.sign(
      { userId, username: user.username, email: user.email },
      process.env.JWT_SECRET,
      { expiresIn: "7d" }
    );
    res.json({ token, user: { id: userId, username: user.username, email: user.email } });
  } catch (err) {
    console.error("Signin error:", err);
    res.status(500).json({ error: "Signin failed" });
  }
});

const requireAuth = (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader) return res.status(401).json({ error: "No token" });
    const token = authHeader.split(" ")[1];
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.userId = decoded.userId.toString();
    next();
  } catch (err) {
    return res.status(401).json({ error: "Invalid token" });
  }
};

/* ================= HELPERS ================= */

const cleanImages = (images = []) => {
  if (!Array.isArray(images)) return [];
  return images
    .filter((img) => img && img.data && img.mimeType)
    .map((img) => ({ data: img.data, mimeType: img.mimeType }));
};

const cleanMessages = (messages = []) => {
  if (!Array.isArray(messages)) return [];
  return messages.map((msg) => ({
    role: msg.role,
    content: msg.content || "",
    images: cleanImages(msg.images || []),
  }));
};

/* ================= CHAT ENDPOINTS ================= */

app.post("/api/chats", requireAuth, async (req, res) => {
  const { text, images = [] } = req.body;
  const userId = req.userId;
  try {
    const firstMessage = {
      role: "user",
      content: text || "",
      images: cleanImages(images),
    };
    const newChat = new Chat({ userId, messages: [firstMessage] });
    const savedChat = await newChat.save();
    const title = text ? text.substring(0, 40) : "New Chat";
    let userChatsDoc = await UserChat.findOne({ userId });
    if (!userChatsDoc) {
      userChatsDoc = new UserChat({
        userId,
        chats: [{ _id: savedChat._id, title, starred: false, createdAt: savedChat.createdAt }],
      });
      await userChatsDoc.save();
    } else {
      await UserChat.updateOne(
        { userId },
        { $push: { chats: { _id: savedChat._id, title, starred: false, createdAt: savedChat.createdAt } } }
      );
    }
    res.status(201).json(savedChat);
  } catch (error) {
    console.error("Create chat error:", error);
    res.status(500).json({ error: "Error Creating Chat" });
  }
});

app.get("/api/chats/:chatId", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;
  try {
    const chat = await Chat.findOne({ _id: chatId, userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    res.json(chat);
  } catch (error) {
    console.error("Fetch chat error:", error);
    res.status(500).json({ error: "Failed to fetch chat" });
  }
});

app.post("/api/chats/:chatId/messages", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;
  const { messages } = req.body;
  try {
    const chat = await Chat.findOne({ _id: chatId, userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    const safeMessages = cleanMessages(messages);
    chat.messages.push(...safeMessages);
    await chat.save();
    res.json(chat);
  } catch (error) {
    console.error("Save messages error:", error);
    res.status(500).json({ error: "Failed to save messages" });
  }
});

app.get("/api/userchats", requireAuth, async (req, res) => {
  const userId = req.userId;
  try {
    const userChatsDoc = await UserChat.findOne({ userId });
    res.json(userChatsDoc || { chats: [] });
  } catch (error) {
    console.error("Fetch user chats error:", error);
    res.status(500).json({ error: "Failed to fetch chats" });
  }
});

app.get("/api/userchats/:chatId", requireAuth, async (req, res) => {
  const userId = req.userId;
  const { chatId } = req.params;
  try {
    const userChatsDoc = await UserChat.findOne({ userId });
    if (!userChatsDoc) return res.status(404).json({ error: "No chats found" });
    const chat = userChatsDoc.chats.find((c) => c._id.toString() === chatId);
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    res.json(chat);
  } catch (error) {
    console.error("Fetch single user chat error:", error);
    res.status(500).json({ error: "Failed to fetch chat" });
  }
});

app.patch("/api/userchats/:chatId/rename", requireAuth, async (req, res) => {
  const userId = req.userId;
  const { chatId } = req.params;
  const { title } = req.body;
  if (!title || title.trim() === "") {
    return res.status(400).json({ error: "Title is required" });
  }
  try {
    const userChatsDoc = await UserChat.findOne({ userId });
    if (!userChatsDoc) return res.status(404).json({ error: "User chats not found" });
    const chat = userChatsDoc.chats.id(chatId);
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    chat.title = title.trim();
    await userChatsDoc.save();
    res.json({ message: "Renamed successfully", title: chat.title });
  } catch (error) {
    console.error("Rename error:", error);
    res.status(500).json({ error: "Failed to rename chat" });
  }
});

/* ================= DELETE CHAT ENDPOINT (FIXED) ================= */
app.delete("/api/userchats/:chatId", requireAuth, async (req, res) => {
  const userId = req.userId;
  const { chatId } = req.params;
  try {
    await UserChat.updateOne(
      { userId },
      { $pull: { chats: { _id: new mongoose.Types.ObjectId(chatId) } } }
    );
    await Chat.deleteOne({ _id: chatId, userId });
    res.json({ message: "Chat deleted successfully" });
  } catch (error) {
    console.error("Delete chat error:", error);
    res.status(500).json({ error: "Failed to delete chat" });
  }
});

/* ================= AI / GNS3 INTEGRATION ================= */

const upload = multer({ dest: "uploads/" });
const OUTPUT_BASE = path.join(__dirname, "../StructraNet_AI/output");
const UPLOAD_DIR = path.join(__dirname, "uploads");
if (!fs.existsSync(OUTPUT_BASE)) fs.mkdirSync(OUTPUT_BASE, { recursive: true });
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

app.use("/generated", express.static(OUTPUT_BASE));
app.use("/uploads", express.static(UPLOAD_DIR));

const PYTHON_CMD = process.platform === "win32" ? "python" : "python3";

// ✅ FIXED: Full corrected /api/generate endpoint with image path and platform forcing
app.post("/api/generate", requireAuth, async (req, res) => {
  const { prompt } = req.body;
  if (!prompt || prompt.trim() === "") {
    return res.status(400).json({ error: "Prompt is required" });
  }

  const runId = Date.now();
  const runOutputDir = path.join(OUTPUT_BASE, `run_${runId}`);
  fs.mkdirSync(runOutputDir, { recursive: true });

  const pythonScript = path.join(__dirname, "../StructraNet_AI/run_pipeline.py");
  if (!fs.existsSync(pythonScript)) {
    console.error(`Python script not found: ${pythonScript}`);
    return res.status(500).json({ error: "Pipeline script missing", details: `File not found: ${pythonScript}` });
  }

  // --- Force platform and image path (adjust as needed) ---
  const FORCE_PLATFORM = "c7200";   // or "iou" if you prefer IOU
  const IMAGE_PATH = "C:\\Users\\DELL\\GNS3\\images\\IOS\\c7200-adventerprisek9-mz.153-3.XB12.image";
  // ---------------------------------------------------------

  // Build arguments dynamically
  const pythonArgs = [pythonScript, prompt, "--output-dir", runOutputDir];
  if (FORCE_PLATFORM) {
    pythonArgs.push("--force-platform", FORCE_PLATFORM);
    if (IMAGE_PATH) {
      pythonArgs.push("--image-path", IMAGE_PATH);
    }
  }

  console.log(`[Generate] Running pipeline with args: ${PYTHON_CMD} ${pythonArgs.join(" ")}`);

  const pythonProcess = spawn(PYTHON_CMD, pythonArgs, {
    cwd: path.join(__dirname, "../StructraNet_AI"),
  });

  let stdout = "";
  let stderr = "";
  let timedOut = false;

  const PIPELINE_TIMEOUT_MS = 15 * 60 * 1000; // 5 minutes
  const timeout = setTimeout(() => {
    timedOut = true;
    pythonProcess.kill();
    console.error("Python process timed out after 5 minutes");
  }, PIPELINE_TIMEOUT_MS);

  pythonProcess.stdout.on("data", (data) => {
    const chunk = data.toString();
    stdout += chunk;
    console.log(`[Python stdout] ${chunk}`);
  });

  pythonProcess.stderr.on("data", (data) => {
    const chunk = data.toString();
    stderr += chunk;
    console.error(`[Python stderr] ${chunk}`);
  });

  pythonProcess.on("error", (err) => {
    clearTimeout(timeout);
    console.error(`Failed to start Python process: ${err.message}`);
    return res.status(500).json({ error: "Could not start Python process", details: err.message });
  });

  pythonProcess.on("close", (code) => {
    clearTimeout(timeout);

    if (timedOut) {
      return res.status(500).json({
        error: "Pipeline timeout",
        details: "Generation took too long (5 minutes). Try a simpler network description.",
      });
    }

    const fullLog = (stdout + stderr).trim();

    if (code !== 0) {
      console.error(`Python exited with code ${code}`);
      console.error(`stderr: ${stderr}`);

      // Friendly error messages
      let friendlyError = "Generation failed. Please try again.";
      if (stderr.includes("ImportError") || stderr.includes("ModuleNotFoundError")) {
        friendlyError = "Missing Python dependency. Run: pip install -r requirements.txt";
      } else if (stderr.includes("401") || stderr.includes("Unauthorized") || stderr.includes("API key")) {
        friendlyError = "AI API key is invalid or missing. Check your .env file.";
      } else if (stderr.includes("ValidationError") || stderr.includes("Too many links")) {
        friendlyError = "Network is too complex for the selected router type. Try reducing the number of devices.";
      } else if (stderr.includes("TimeoutError") || stderr.includes("timeout")) {
        friendlyError = "AI request timed out. Please try again.";
      } else if (stderr.includes("JSONDecodeError") || stderr.includes("json")) {
        friendlyError = "AI returned an unexpected response. Please try rephrasing your request.";
      }

      return res.status(500).json({
        success: false,
        error: friendlyError,
        details: process.env.NODE_ENV === "development" ? stderr : undefined,
      });
    }

    const match = stdout.match(/GNS3PROJECT_PATH=(.+)/);
    if (!match) {
      console.error(`Could not find GNS3PROJECT_PATH in stdout:\n${stdout}`);
      return res.status(500).json({
        success: false,
        error: "Could not locate the generated file. Please try again.",
        details: fullLog,
      });
    }

    const projectPath = match[1].trim();
    if (!fs.existsSync(projectPath)) {
      console.error(`Output file not found at: ${projectPath}`);
      return res.status(500).json({
        success: false,
        error: "Output file was not created. Please try again.",
        details: `Expected path: ${projectPath}`,
      });
    }

    const fileName = path.basename(projectPath);
    const finalFilePath = path.join(OUTPUT_BASE, `run_${runId}`, fileName);
    if (projectPath !== finalFilePath) {
      fs.renameSync(projectPath, finalFilePath);
    }
    const downloadUrl = `/generated/run_${runId}/${fileName}`;

    res.json({
      success: true,
      downloadUrl: downloadUrl,
      log: fullLog,
      filename: fileName,
    });
  });
});

app.post("/api/upload", requireAuth, upload.single("file"), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: "No file uploaded" });
  }
  const originalName = req.file.originalname;
  const ext = path.extname(originalName).toLowerCase();
  if (ext !== ".gns3project") {
    fs.unlinkSync(req.file.path);
    return res.status(400).json({ error: "Only .gns3project files are allowed" });
  }
  const newPath = path.join(UPLOAD_DIR, originalName);
  fs.renameSync(req.file.path, newPath);
  const downloadUrl = `/uploads/${originalName}`;
  res.json({ message: "File uploaded successfully", downloadUrl, filename: originalName });
});

/* ================= START SERVER ================= */

app.listen(port, () => {
  connect();
  console.log(`🚀 Server running on port ${port}`);
  console.log(`🐍 Python command: ${PYTHON_CMD}`);
});