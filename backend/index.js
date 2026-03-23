import express from "express";
import ImageKit from "imagekit";
import dotenv from 'dotenv';
import cors from "cors";
import mongoose from "mongoose";
import { verifyToken } from '@clerk/backend';

import UserChat from "./models/userChat.js";
import Chat from "./models/chat.js";
import dns from "dns"


dns.setServers(["1.1.1.1", "8.8.8.8"]);
dotenv.config();

const port = process.env.PORT || 3000;
const app = express();

app.use(cors({ origin: process.env.CLIENT_URL }));
app.use(express.json());

const connect = async () => {
  try {
    await mongoose.connect(process.env.MONGO);
    console.log("✅ Connected to MongoDB");
  } catch (error) {
    console.error("❌ MongoDB connection error:", error.message);
    process.exit(1);
  }
};

const imagekit = new ImageKit({
  privateKey: process.env.IMAGE_KIT_PRIVATE_KEY,
  publicKey: process.env.IMAGE_KIT_PUBLIC_KEY,
  urlEndpoint: process.env.IMAGE_KIT_ENDPOINT,
});

app.get("/api/upload", (req, res) => {
  const result = imagekit.getAuthenticationParameters();
  res.send(result);
});

// Middleware للتحقق من المصادقة باستخدام JWT Key
const requireAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;
    if (!authHeader) {
      console.log("❌ No Authorization header");
      return res.status(401).json({ error: "No token provided" });
    }

    const token = authHeader.split(' ')[1];
    if (!token) {
      console.log("❌ Token missing after Bearer");
      return res.status(401).json({ error: "Malformed token" });
    }

    // تسجيل جزء صغير من التوكن للتصحيح (آمن)
    

    // التحقق من التوكن باستخدام المفتاح العام
    const session = await verifyToken(token, { 
      jwtKey: process.env.CLERK_JWT_KEY,
      // يمكن إضافة خيارات أخرى إذا لزم الأمر
    });

    if (!session || !session.sub) {
      console.log("❌ Invalid token payload");
      return res.status(401).json({ error: "Invalid token" });
    }

    req.userId = session.sub;
    
    next();
  } catch (error) {
    console.error("❌ Auth error details:", {
      name: error.name,
      message: error.message,
      reason: error.reason,
      stack: error.stack,
    });

    // رسائل خطأ مخصصة حسب نوع الخطأ
    if (error.message?.includes('Invalid JWT form')) {
      return res.status(401).json({ error: "Invalid token format" });
    }
    if (error.message?.includes('jwt expired')) {
      return res.status(401).json({ error: "Token expired" });
    }
    if (error.message?.includes('invalid signature')) {
      return res.status(401).json({ error: "Invalid signature" });
    }

    res.status(401).json({ error: "Authentication failed" });
  }
};

// إنشاء محادثة جديدة (محمية)
app.post("/api/chats", requireAuth, async (req, res) => {
  const { text, images = [] } = req.body;
  const userId = req.userId;

  try {
    const firstMessage = { role: "user", content: text || "", images };
    const newChat = new Chat({ userId, messages: [firstMessage] });
    const savedChat = await newChat.save();

    let userChatsDoc = await UserChat.findOne({ userId });
    const title = text ? text.substring(0, 40) : "New Chat";

    if (!userChatsDoc) {
      userChatsDoc = new UserChat({
        userId,
        chats: [{ _id: savedChat._id, title, createdAt: savedChat.createdAt }],
      });
      await userChatsDoc.save();
    } else {
      await UserChat.updateOne(
        { userId },
        { $push: { chats: { _id: savedChat._id, title, createdAt: savedChat.createdAt } } }
      );
    }

    res.status(201).json(savedChat);
  } catch (error) {
    console.error("❌ Error creating chat:", error);
    res.status(500).send("Error Creating Chat!!");
  }
});

// جلب محادثة محددة
app.get("/api/chats/:chatId", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;
  try {
    const chat = await Chat.findOne({ _id: chatId, userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    res.json(chat);
  } catch (error) {
    console.error("Error fetching chat:", error);
    res.status(500).json({ error: "Failed to fetch chat" });
  }
});

// إضافة رسائل إلى محادثة
app.post("/api/chats/:chatId/messages", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;
  const { messages } = req.body;

  try {
    const chat = await Chat.findOne({ _id: chatId, userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });
    chat.messages.push(...messages);
    await chat.save();
    res.json(chat);
  } catch (error) {
    console.error("Error saving messages:", error);
    res.status(500).json({ error: "Failed to save messages" });
  }
});

// إعادة إنشاء آخر رد AI
app.post("/api/chats/:chatId/regenerate", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;

  try {
    const chat = await Chat.findOne({ _id: chatId, userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });

    const lastMessage = chat.messages[chat.messages.length - 1];
    if (lastMessage && lastMessage.role === 'assistant') {
      chat.messages.pop();
    }

    const userMessages = chat.messages.filter(m => m.role === 'user');
    const lastUserMessage = userMessages[userMessages.length - 1];
    if (!lastUserMessage) return res.status(400).json({ error: "No user message to regenerate from" });

    // هنا يجب استدعاء Gemini API مع السياق الكامل
    // سنقوم برد وهمي الآن
    const newReply = { role: 'assistant', content: "This is a regenerated response (placeholder)." };
    chat.messages.push(newReply);
    await chat.save();

    res.json({ message: newReply });
  } catch (error) {
    console.error("Error regenerating:", error);
    res.status(500).json({ error: "Failed to regenerate" });
  }
});

// مشاركة المحادثة
app.post("/api/chats/:chatId/share", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;

  try {
    const shareUrl = `${process.env.CLIENT_URL}/dashboard/chats/${chatId}`;
    res.json({ shareUrl });
  } catch (error) {
    console.error("Error sharing:", error);
    res.status(500).json({ error: "Failed to share" });
  }
});

// جلب محادثات المستخدم
app.get("/api/userchats", requireAuth, async (req, res) => {
  const userId = req.userId;
  try {
    const userChatsDoc = await UserChat.findOne({ userId });
    res.json(userChatsDoc || { chats: [] });
  } catch (error) {
    console.error("Error fetching user chats:", error);
    res.status(500).json({ error: "Failed to fetch chats" });
  }
});

app.listen(port, () => {
  connect();
  console.log(`🚀 Server running on port ${port}`);
});
/* import dns from "dns";
dns.setServers(["1.1.1.1", "8.8.8.8"]);*/