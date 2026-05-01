import mongoose from "mongoose";

const imageSchema = new mongoose.Schema({
  data: { type: String, required: true },      // base64
  mimeType: { type: String, required: true },  // image/png أو image/jpeg
});

const messageSchema = new mongoose.Schema({
  role: { type: String, enum: ["user", "assistant"], required: true },
  content: { type: String, default: "" },

  // ✅ بدل string links → object فيه الصورة نفسها
  images: { type: [imageSchema], default: [] },

}, { timestamps: true });

const chatSchema = new mongoose.Schema({
  userId: { type: String, required: true },
  messages: [messageSchema],
}, { timestamps: true });

export default mongoose.models.Chat || mongoose.model("Chat", chatSchema);