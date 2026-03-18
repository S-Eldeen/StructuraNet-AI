import mongoose from "mongoose";

const userChatsSchema = new mongoose.Schema({
  userId: { type: String, required: true, unique: true },
  chats: [
    {
      _id: { type: mongoose.Schema.Types.ObjectId, ref: "Chat", required: true },
      title: { type: String, required: true },
      createdAt: { type: Date, default: Date.now },
    },
  ],
}, { timestamps: true });

export default mongoose.models.UserChat || mongoose.model("UserChat", userChatsSchema);