const mongoose = require("mongoose");

const chatSchema = new mongoose.Schema(
  {
    repo: { type: String, required: true },
    title: { type: String, default: "New chat" },
  },
  { timestamps: true },
);

module.exports = mongoose.model("Chat", chatSchema);
