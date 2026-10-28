const mongoose = require("mongoose");

const chatSchema = new mongoose.Schema(
  {
    repo: { type: String, required: true },
    user: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
      index: true,
    },
    title: { type: String, default: "New chat" },
  },
  { timestamps: true },
);

module.exports = mongoose.model("Chat", chatSchema);
