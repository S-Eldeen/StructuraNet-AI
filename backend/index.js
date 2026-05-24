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

// ── Validate critical env vars at startup ────────────────────────────────────
if (!process.env.JWT_SECRET) {
  console.error("❌ FATAL: JWT_SECRET is not set in .env");
  process.exit(1);
}
if (!process.env.MONGO) {
  console.error("❌ FATAL: MONGO connection string is not set in .env");
  process.exit(1);
}

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const port = process.env.PORT || 3000;
const IS_DEV = process.env.NODE_ENV !== "production";
const app = express();

app.use(
  cors({
    origin: (origin, cb) => {
      if (!origin || origin.startsWith("http://localhost:")) return cb(null, true);
      cb(new Error("Not allowed by CORS"));
    },
    credentials: true,
  })
);
app.use(express.json({ limit: "25mb" }));
app.use(express.urlencoded({ extended: true, limit: "25mb" }));

// ── MongoDB ──────────────────────────────────────────────────────────────────
const connect = async () => {
  try {
    await mongoose.connect(process.env.MONGO);
    console.log("✅ Connected to MongoDB");
  } catch (err) {
    console.error("❌ MongoDB error:", err.message);
    process.exit(1);
  }
};

// ── Auth middleware ───────────────────────────────────────────────────────────
const requireAuth = (req, res, next) => {
  try {
    const header = req.headers.authorization || "";
    // Support Bearer token (API) and ?token= query param (for direct file downloads)
    const token = header.startsWith("Bearer ") ? header.split(" ")[1] : req.query.token;
    if (!token) return res.status(401).json({ error: "No token provided" });
    const decoded = jwt.verify(token, process.env.JWT_SECRET);
    req.userId = decoded.userId.toString();
    next();
  } catch {
    res.status(401).json({ error: "Invalid or expired token" });
  }
};

// ── Input sanitizers ─────────────────────────────────────────────────────────
const cleanImages = (imgs = []) =>
  Array.isArray(imgs)
    ? imgs.filter((i) => i?.data && i?.mimeType).map((i) => ({ data: i.data, mimeType: i.mimeType }))
    : [];

const cleanMessages = (msgs = []) =>
  Array.isArray(msgs)
    ? msgs.map((m) => ({ role: m.role, content: m.content || "", images: cleanImages(m.images) }))
    : [];

// ─────────────────────────────────────────────────────────────────────────────
//  Auth
// ─────────────────────────────────────────────────────────────────────────────
app.post("/api/auth/signup", async (req, res) => {
  try {
    const { username, email, password } = req.body;
    if (!username || !email || !password) return res.status(400).json({ error: "All fields are required" });
    if (await User.findOne({ email })) return res.status(400).json({ error: "Email already exists" });
    const hash = await bcrypt.hash(password, 12);
    await User.create({ username, email, password: hash });
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
    if (!user || !(await bcrypt.compare(password, user.password)))
      return res.status(400).json({ error: "Invalid credentials" });
    const token = jwt.sign(
      { userId: user._id.toString(), username: user.username, email: user.email },
      process.env.JWT_SECRET,
      { expiresIn: "7d" }
    );
    res.json({ token, user: { id: user._id, username: user.username, email: user.email } });
  } catch (err) {
    console.error("Signin error:", err);
    res.status(500).json({ error: "Signin failed" });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
//  Chat CRUD
// ─────────────────────────────────────────────────────────────────────────────
app.post("/api/chats", requireAuth, async (req, res) => {
  const { text, images = [] } = req.body;
  try {
    const newChat = new Chat({
      userId: req.userId,
      messages: [{ role: "user", content: text || "", images: cleanImages(images) }],
    });
    const saved = await newChat.save();
    const title = text?.substring(0, 40) || "New Chat";
    await UserChat.findOneAndUpdate(
      { userId: req.userId },
      { $push: { chats: { _id: saved._id, title, starred: false, createdAt: saved.createdAt } } },
      { upsert: true }
    );
    res.status(201).json(saved);
  } catch (err) {
    console.error("Create chat error:", err);
    res.status(500).json({ error: "Error creating chat" });
  }
});

app.get("/api/chats/:chatId", requireAuth, async (req, res) => {
  try {
    const chat = await Chat.findOne({ _id: req.params.chatId, userId: req.userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    res.json(chat);
  } catch {
    res.status(500).json({ error: "Failed to fetch chat" });
  }
});

app.post("/api/chats/:chatId/messages", requireAuth, async (req, res) => {
  try {
    const chat = await Chat.findOne({ _id: req.params.chatId, userId: req.userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    chat.messages.push(...cleanMessages(req.body.messages || []));
    await chat.save();
    res.json(chat);
  } catch (err) {
    console.error("Save messages error:", err);
    res.status(500).json({ error: "Failed to save messages" });
  }
});

app.get("/api/userchats", requireAuth, async (req, res) => {
  try {
    const doc = await UserChat.findOne({ userId: req.userId });
    res.json(doc || { chats: [] });
  } catch {
    res.status(500).json({ error: "Failed to fetch chats" });
  }
});

app.patch("/api/userchats/:chatId/rename", requireAuth, async (req, res) => {
  const { title } = req.body;
  if (!title?.trim()) return res.status(400).json({ error: "Title is required" });
  try {
    const doc = await UserChat.findOne({ userId: req.userId });
    if (!doc) return res.status(404).json({ error: "User chats not found" });
    const chat = doc.chats.id(req.params.chatId);
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    chat.title = title.trim();
    await doc.save();
    res.json({ message: "Renamed successfully", title: chat.title });
  } catch (err) {
    console.error("Rename error:", err);
    res.status(500).json({ error: "Failed to rename chat" });
  }
});

app.patch("/api/userchats/:chatId/star", requireAuth, async (req, res) => {
  const { starred } = req.body;
  if (typeof starred !== "boolean") return res.status(400).json({ error: "starred must be a boolean" });
  try {
    const result = await UserChat.updateOne(
      { userId: req.userId, "chats._id": req.params.chatId },
      { $set: { "chats.$.starred": starred } }
    );
    if (result.matchedCount === 0) return res.status(404).json({ error: "Chat not found" });
    res.json({ message: "Star updated", starred });
  } catch (err) {
    console.error("Star error:", err);
    res.status(500).json({ error: "Failed to update star" });
  }
});

app.delete("/api/userchats/:chatId", requireAuth, async (req, res) => {
  try {
    await UserChat.updateOne(
      { userId: req.userId },
      { $pull: { chats: { _id: new mongoose.Types.ObjectId(req.params.chatId) } } }
    );
    await Chat.deleteOne({ _id: req.params.chatId, userId: req.userId });
    res.json({ message: "Chat deleted successfully" });
  } catch (err) {
    console.error("Delete error:", err);
    res.status(500).json({ error: "Failed to delete chat" });
  }
});

// ─────────────────────────────────────────────────────────────────────────────
//  AI / GNS3 Pipeline
// ─────────────────────────────────────────────────────────────────────────────
const upload = multer({ dest: "uploads/" });
const OUTPUT_BASE = path.join(__dirname, "../StructraNet_AI/output");
const UPLOAD_DIR = path.join(__dirname, "uploads");
const PYTHON_CMD = process.platform === "win32" ? "python" : "python3";

if (!fs.existsSync(OUTPUT_BASE)) fs.mkdirSync(OUTPUT_BASE, { recursive: true });
if (!fs.existsSync(UPLOAD_DIR)) fs.mkdirSync(UPLOAD_DIR, { recursive: true });

// Static for uploads (less sensitive)
app.use("/uploads", express.static(UPLOAD_DIR));

const FORCE_PLATFORM = process.env.FORCE_PLATFORM || "c7200";
const IOS_IMAGE_PATH = process.env.IOS_IMAGE_PATH || "";

// Rate limiter: 5 requests per minute per user
const rateLimitMap = new Map();
const RATE_LIMIT = 5;

function checkRateLimit(userId) {
  const now = Date.now();
  const rec = rateLimitMap.get(userId) || { count: 0, resetAt: now + 60000 };
  if (now > rec.resetAt) {
    rec.count = 0;
    rec.resetAt = now + 60000;
  }
  if (rec.count >= RATE_LIMIT) {
    const wait = Math.ceil((rec.resetAt - now) / 1000);
    return { limited: true, wait };
  }
  rec.count++;
  rateLimitMap.set(userId, rec);
  return { limited: false };
}

app.post("/api/generate", requireAuth, async (req, res) => {
  const { prompt } = req.body;
  if (!prompt?.trim()) return res.status(400).json({ error: "Prompt is required" });
  if (prompt.length > 4000) return res.status(400).json({ error: "Prompt too long (max 4000 chars)" });

  const rl = checkRateLimit(req.userId);
  if (rl.limited) return res.status(429).json({ error: `Rate limit exceeded. Try again in ${rl.wait}s` });

  const runId = Date.now();
  const runOutputDir = path.join(OUTPUT_BASE, `run_${runId}`);
  fs.mkdirSync(runOutputDir, { recursive: true });

  const pythonScript = path.join(__dirname, "../StructraNet_AI/run_pipeline.py");
  if (!fs.existsSync(pythonScript)) return res.status(500).json({ error: "Pipeline script not found" });

  const pythonArgs = [pythonScript, prompt, "--output-dir", runOutputDir];
  if (FORCE_PLATFORM) {
    pythonArgs.push("--force-platform", FORCE_PLATFORM);
    if (IOS_IMAGE_PATH.trim()) pythonArgs.push("--image-path", IOS_IMAGE_PATH);
  }

  console.log(`▶ [run_${runId}] user=${req.userId} platform=${FORCE_PLATFORM}`);

  const proc = spawn(PYTHON_CMD, pythonArgs, {
    cwd: path.join(__dirname, "../StructraNet_AI"),
  });

  let stdout = "";
  let stderr = "";
  let timedOut = false;

  const killTimer = setTimeout(() => {
    timedOut = true;
    proc.kill();
    console.error(`⏱ [run_${runId}] Timed out after 15 minutes`);
  }, 15 * 60 * 1000);

  proc.stdout.on("data", (d) => {
    stdout += d.toString();
  });
  proc.stderr.on("data", (d) => {
    stderr += d.toString();
  });

  proc.on("error", (err) => {
    clearTimeout(killTimer);
    console.error("Spawn error:", err.message);
    res.status(500).json({ error: "Could not start pipeline", details: IS_DEV ? err.message : undefined });
  });

  proc.on("close", (code) => {
    clearTimeout(killTimer);

    if (timedOut) return res.status(504).json({ error: "Generation timed out (15 min). Try a simpler request." });

    const fullLog = (stdout + stderr).trim();

    if (code !== 0) {
      let friendlyError = "Generation failed. Please try again.";
      if (stderr.includes("ImportError") || stderr.includes("ModuleNotFoundError"))
        friendlyError = "Missing Python dependency. Run: pip install -r requirements.txt";
      else if (stderr.includes("401") || stderr.includes("API key") || stderr.includes("Unauthorized"))
        friendlyError = "AI API key is invalid or missing. Check .env file.";
      else if (stderr.includes("Too many links") || stderr.includes("ValidationError"))
        friendlyError = "Network too complex for selected router. Try reducing devices.";
      else if (stderr.includes("timeout") || stderr.includes("TimeoutError"))
        friendlyError = "AI request timed out. Try again.";
      else if (stderr.includes("JSONDecodeError") || stderr.includes("json"))
        friendlyError = "AI returned unexpected response. Rephrase your request.";

      return res.status(500).json({
        success: false,
        error: friendlyError,
        details: IS_DEV ? fullLog : undefined,
      });
    }

    const match = stdout.match(/GNS3PROJECT_PATH=(.+)/);
    if (!match)
      return res.status(500).json({
        success: false,
        error: "Could not locate the generated file.",
        details: IS_DEV ? fullLog : undefined,
      });

    const projectPath = match[1].trim();
    if (!fs.existsSync(projectPath))
      return res.status(500).json({ success: false, error: "Output file was not created." });

    const fileName = path.basename(projectPath);
    const finalPath = path.join(runOutputDir, fileName);
    if (path.resolve(projectPath) !== path.resolve(finalPath)) fs.renameSync(projectPath, finalPath);

    // Auth-protected download URL (not public)
    const downloadUrl = `/api/download/${runId}/${encodeURIComponent(fileName)}`;

    // --- Return FULL log (not truncated) as requested ---
    console.log(`✅ [run_${runId}] Generated: ${fileName}`);
    res.json({ success: true, downloadUrl, log: fullLog, filename: fileName });

    // Cleanup old runs (keep last 20)
    cleanupOldRuns();
  });
});

// ── Protected file download endpoint ─────────────────────────────────────────
app.get("/api/download/:runId/:filename", requireAuth, (req, res) => {
  const { runId, filename } = req.params;
  const safeFilename = path.basename(decodeURIComponent(filename));

  // Path traversal protection
  if (safeFilename.includes("..") || runId.includes("..")) return res.status(400).json({ error: "Invalid path" });

  const filePath = path.join(OUTPUT_BASE, `run_${runId}`, safeFilename);
  if (!fs.existsSync(filePath)) return res.status(404).json({ error: "File not found or expired" });

  res.download(filePath, safeFilename);
});

// ── Cleanup old runs (keep last 20 to save disk space) ───────────────────────
function cleanupOldRuns() {
  try {
    const dirs = fs
      .readdirSync(OUTPUT_BASE)
      .filter((d) => d.startsWith("run_"))
      .map((d) => ({ name: d, time: parseInt(d.split("_")[1]) || 0 }))
      .sort((a, b) => b.time - a.time);

    const toDelete = dirs.slice(20); // keep only the 20 most recent
    toDelete.forEach((d) => {
      try {
        fs.rmSync(path.join(OUTPUT_BASE, d.name), { recursive: true, force: true });
      } catch {
        /* ignore */
      }
    });
    if (toDelete.length > 0) console.log(`🧹 Cleaned up ${toDelete.length} old run(s)`);
  } catch {
    /* ignore cleanup errors */
  }
}

// ── File upload ───────────────────────────────────────────────────────────────
app.post("/api/upload", requireAuth, upload.single("file"), (req, res) => {
  if (!req.file) return res.status(400).json({ error: "No file uploaded" });
  const ext = path.extname(req.file.originalname).toLowerCase();
  if (ext !== ".gns3project") {
    fs.unlinkSync(req.file.path);
    return res.status(400).json({ error: "Only .gns3project files are allowed" });
  }
  const newPath = path.join(UPLOAD_DIR, req.file.originalname);
  fs.renameSync(req.file.path, newPath);
  res.json({
    message: "Uploaded",
    downloadUrl: `/uploads/${req.file.originalname}`,
    filename: req.file.originalname,
  });
});

// ─────────────────────────────────────────────────────────────────────────────
//  Start
// ─────────────────────────────────────────────────────────────────────────────
app.listen(port, () => {
  connect();
  console.log(`🚀 Backend    → http://localhost:${port}`);
  console.log(`🐍 Python     → ${PYTHON_CMD}`);
  console.log(`📦 Platform   → ${FORCE_PLATFORM}`);
  console.log(`🌍 Mode       → ${IS_DEV ? "development" : "production"}`);
});