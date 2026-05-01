import express from "express";
import dotenv from "dotenv";
import cors from "cors";
import mongoose from "mongoose";
import jwt from "jsonwebtoken";
import bcrypt from "bcryptjs";
import User from "./models/User.js";
import UserChat from "./models/userChat.js";
import Chat from "./models/chat.js";
import dns from "dns";

dns.setServers(["1.1.1.1", "8.8.8.8"]);
dotenv.config();

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

// مهم عشان الصور Base64 حجمها كبير
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

    await User.create({
      username,
      email,
      password: hashedPassword,
    });

    res.status(201).json({ message: "User created successfully" });
  } catch (err) {
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

    const token = jwt.sign({ userId: user._id }, process.env.JWT_SECRET, {
      expiresIn: "7d",
    });

    res.json({
      token,
      user: {
        id: user._id,
        username: user.username,
        email: user.email,
      },
    });
  } catch (err) {
    res.status(500).json({ error: "Signin failed" });
  }
});

const requireAuth = (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader) return res.status(401).json({ error: "No token" });

    const token = authHeader.split(" ")[1];
    const decoded = jwt.verify(token, process.env.JWT_SECRET);

    req.userId = decoded.userId;
    next();
  } catch {
    return res.status(401).json({ error: "Invalid token" });
  }
};

/* ================= HELPERS ================= */

const cleanImages = (images = []) => {
  if (!Array.isArray(images)) return [];

  return images
    .filter((img) => img && img.data && img.mimeType)
    .map((img) => ({
      data: img.data,
      mimeType: img.mimeType,
    }));
};

const cleanMessages = (messages = []) => {
  if (!Array.isArray(messages)) return [];

  return messages.map((msg) => ({
    role: msg.role,
    content: msg.content || "",
    images: cleanImages(msg.images || []),
  }));
};

/* ================= API ================= */

/* ==== CREATE CHAT ==== */
app.post("/api/chats", requireAuth, async (req, res) => {
  const { text, images = [] } = req.body;
  const userId = req.userId;

  try {
    const firstMessage = {
      role: "user",
      content: text || "",
      images: cleanImages(images),
    };

    const newChat = new Chat({
      userId,
      messages: [firstMessage],
    });

    const savedChat = await newChat.save();

    const title = text ? text.substring(0, 40) : "New Chat";

    let userChatsDoc = await UserChat.findOne({ userId });

    if (!userChatsDoc) {
      userChatsDoc = new UserChat({
        userId,
        chats: [
          {
            _id: savedChat._id,
            title,
            starred: false,
            createdAt: savedChat.createdAt,
          },
        ],
      });
      await userChatsDoc.save();
    } else {
      await UserChat.updateOne(
        { userId },
        {
          $push: {
            chats: {
              _id: savedChat._id,
              title,
              starred: false,
              createdAt: savedChat.createdAt,
            },
          },
        }
      );
    }

    res.status(201).json(savedChat);
  } catch (error) {
    console.error("Create chat error:", error);
    res.status(500).json({ error: "Error Creating Chat" });
  }
});

/* ==== GET CHAT ==== */
app.get("/api/chats/:chatId", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;

  try {
    const chat = await Chat.findOne({ _id: chatId, userId });

    if (!chat) {
      return res.status(404).json({ error: "Chat not found" });
    }

    res.json(chat);
  } catch (error) {
    res.status(500).json({ error: "Failed to fetch chat" });
  }
});

/* ==== ADD MESSAGE ==== */
app.post("/api/chats/:chatId/messages", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;
  const { messages } = req.body;

  try {
    const chat = await Chat.findOne({ _id: chatId, userId });

    if (!chat) {
      return res.status(404).json({ error: "Chat not found" });
    }

    const safeMessages = cleanMessages(messages);
    chat.messages.push(...safeMessages);

    await chat.save();

    res.json(chat);
  } catch (error) {
    console.error("Save messages error:", error);
    res.status(500).json({ error: "Failed to save messages" });
  }
});

/* ==== USER CHATS ==== */
app.get("/api/userchats", requireAuth, async (req, res) => {
  const userId = req.userId;

  try {
    const userChatsDoc = await UserChat.findOne({ userId });
    res.json(userChatsDoc || { chats: [] });
  } catch (error) {
    res.status(500).json({ error: "Failed to fetch chats" });
  }
});

app.listen(port, () => {
  connect();
  console.log(`🚀 Server running on port ${port}`);
});