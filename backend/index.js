import express from "express";
import ImageKit from "imagekit";
import dotenv from "dotenv";
import cors from "cors";
import mongoose from "mongoose";
import { verifyToken } from "@clerk/backend";
import UserChat from "./models/userChat.js";
import Chat from "./models/chat.js";
import dns from "dns";

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

const requireAuth = async (req, res, next) => {
  try {
    const authHeader = req.headers.authorization;

    if (!authHeader || !authHeader.startsWith("Bearer ")) {
      return res.status(401).json({
        error: "NO_TOKEN",
        message: "No token provided",
      });
    }

    const token = authHeader.split(" ")[1];

    if (!token) {
      return res.status(401).json({
        error: "MALFORMED_TOKEN",
        message: "Malformed token",
      });
    }

    const session = await verifyToken(token, {
  jwtKey: process.env.CLERK_JWT_KEY,
  clockSkewInMs: 300000,
});

    if (!session?.sub) {
      return res.status(401).json({
        error: "INVALID_TOKEN",
        message: "Invalid token",
      });
    }

    req.userId = session.sub;
    next();
  } catch (error) {
    const reason = error?.reason || "";
    const message = error?.message || "";

    console.error("❌ Auth error:", {
      reason,
      message,
    });

    if (
      reason === "token-expired" ||
      message.includes("jwt expired") ||
      message.includes("expired")
    ) {
      return res.status(401).json({
        error: "TOKEN_EXPIRED",
        message: "Session expired. Please sign in again.",
        shouldLogout: true,
      });
    }

    if (
      reason === "token-invalid" ||
      message.includes("Invalid JWT") ||
      message.includes("Invalid JWT form") ||
      message.includes("invalid signature")
    ) {
      return res.status(401).json({
        error: "INVALID_TOKEN",
        message: "Invalid session. Please sign in again.",
        shouldLogout: true,
      });
    }

    return res.status(401).json({
      error: "AUTHENTICATION_FAILED",
      message: "Authentication failed",
      shouldLogout: true,
    });
  }
};

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
        {
          $push: {
            chats: {
              _id: savedChat._id,
              title,
              createdAt: savedChat.createdAt,
            },
          },
        }
      );
    }

    res.status(201).json(savedChat);
  } catch (error) {
    console.error("❌ Error creating chat:", error);
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
    console.error("Error fetching chat:", error);
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

    chat.messages.push(...messages);
    await chat.save();

    res.json(chat);
  } catch (error) {
    console.error("Error saving messages:", error);
    res.status(500).json({ error: "Failed to save messages" });
  }
});

app.post("/api/chats/:chatId/regenerate", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;

  try {
    const chat = await Chat.findOne({ _id: chatId, userId });
    if (!chat) return res.status(404).json({ error: "Chat not found" });

    const lastMessage = chat.messages[chat.messages.length - 1];
    if (lastMessage && lastMessage.role === "assistant") {
      chat.messages.pop();
    }

    const userMessages = chat.messages.filter((m) => m.role === "user");
    const lastUserMessage = userMessages[userMessages.length - 1];

    if (!lastUserMessage) {
      return res.status(400).json({ error: "No user message to regenerate from" });
    }

    const newReply = {
      role: "assistant",
      content: "This is a regenerated response (placeholder).",
    };

    chat.messages.push(newReply);
    await chat.save();

    res.json({ message: newReply });
  } catch (error) {
    console.error("Error regenerating:", error);
    res.status(500).json({ error: "Failed to regenerate" });
  }
});

app.post("/api/chats/:chatId/share", requireAuth, async (req, res) => {
  const { chatId } = req.params;

  try {
    const shareUrl = `${process.env.CLIENT_URL}/dashboard/chats/${chatId}`;
    res.json({ shareUrl });
  } catch (error) {
    console.error("Error sharing:", error);
    res.status(500).json({ error: "Failed to share" });
  }
});

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

app.patch("/api/userchats/:chatId/rename", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const { title } = req.body;
  const userId = req.userId;

  if (!title || !title.trim()) {
    return res.status(400).json({ error: "Title is required" });
  }

  try {
    const result = await UserChat.updateOne(
      { userId, "chats._id": chatId },
      { $set: { "chats.$.title": title.trim() } }
    );

    if (result.matchedCount === 0) {
      return res.status(404).json({ error: "Chat not found" });
    }

    res.json({ success: true });
  } catch (error) {
    console.error("Error renaming chat:", error);
    res.status(500).json({ error: "Failed to rename chat" });
  }
});

app.patch("/api/userchats/:chatId/star", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const { starred } = req.body;
  const userId = req.userId;

  try {
    const result = await UserChat.updateOne(
      { userId, "chats._id": chatId },
      { $set: { "chats.$.starred": starred } }
    );

    if (result.matchedCount === 0) {
      return res.status(404).json({ error: "Chat not found" });
    }

    res.json({ success: true, starred });
  } catch (error) {
    console.error("Error starring chat:", error);
    res.status(500).json({ error: "Failed to star chat" });
  }
});

app.delete("/api/userchats/:chatId", requireAuth, async (req, res) => {
  const { chatId } = req.params;
  const userId = req.userId;

  try {
    await UserChat.updateOne({ userId }, { $pull: { chats: { _id: chatId } } });
    await Chat.findOneAndDelete({ _id: chatId, userId });

    res.json({ success: true });
  } catch (error) {
    console.error("Error deleting chat:", error);
    res.status(500).json({ error: "Failed to delete chat" });
  }
});

app.listen(port, () => {
  connect();
  console.log(`🚀 Server running on port ${port}`);
});