import mongoose from "mongoose";

const messageSchema = new mongoose.Schema({
  role: { type: String, enum: ["user", "assistant"], required: true },
  content: { type: String, default: "" },
  images: { type: [String], default: [] },
}, { timestamps: true });

const chatSchema = new mongoose.Schema({
  userId: { type: String, required: true },
  messages: [messageSchema],
}, { timestamps: true });

export default mongoose.models.Chat || mongoose.model("Chat", chatSchema);