const express = require("express");
const bcrypt = require("bcryptjs");
const jwt = require("jsonwebtoken");
const { rateLimit } = require("express-rate-limit");
const User = require("./models/User");

const COOKIE = "token";
const baseCookie = {
  httpOnly: true,
  sameSite: "lax",
  secure: process.env.NODE_ENV === "production",
};

function signToken(userId) {
  return jwt.sign({ sub: String(userId) }, process.env.JWT_SECRET, {
    expiresIn: "7d",
  });
}

function requireAuth(req, res, next) {
  const token = req.cookies?.[COOKIE];
  if (!token) return res.status(401).json({ error: "Not logged in." });
  try {
    req.userId = jwt.verify(token, process.env.JWT_SECRET).sub;
    next();
  } catch {
    res.status(401).json({ error: "Not logged in." });
  }
}

const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: "draft-7",
  legacyHeaders: false,
  message: { error: "Too many attempts. Try again later." },
});

function readCredentials(req) {
  return {
    email: String(req.body?.email || "")
      .trim()
      .toLowerCase(),
    password: String(req.body?.password || ""),
  };
}

const router = express.Router();

router.post("/register", authLimiter, async (req, res) => {
  const { email, password } = readCredentials(req);
  if (!/^\S+@\S+\.\S+$/.test(email)) {
    return res.status(400).json({ error: "Enter a valid email." });
  }
  if (password.length < 8 || password.length > 72) {
    return res
      .status(400)
      .json({ error: "Password must be 8 to 72 characters." });
  }
  try {
    const passwordHash = await bcrypt.hash(password, 10);
    const user = await User.create({ email, passwordHash });
    res.cookie(COOKIE, signToken(user._id), {
      ...baseCookie,
      maxAge: 7 * 24 * 60 * 60 * 1000,
    });
    res.status(201).json({ id: user._id, email: user.email });
  } catch (err) {
    if (err.code === 11000) {
      return res.status(409).json({ error: "Email already registered." });
    }
    throw err;
  }
});

router.post("/login", authLimiter, async (req, res) => {
  const { email, password } = readCredentials(req);
  const user = await User.findOne({ email });
  const ok = user && (await bcrypt.compare(password, user.passwordHash));
  if (!ok) {
    return res.status(401).json({ error: "Invalid email or password." });
  }
  res.cookie(COOKIE, signToken(user._id), {
    ...baseCookie,
    maxAge: 7 * 24 * 60 * 60 * 1000,
  });
  res.json({ id: user._id, email: user.email });
});

router.post("/logout", (req, res) => {
  res.clearCookie(COOKIE, baseCookie);
  res.json({ ok: true });
});

router.get("/me", requireAuth, async (req, res) => {
  const user = await User.findById(req.userId);
  if (!user) return res.status(401).json({ error: "Not logged in." });
  res.json({ id: user._id, email: user.email });
});

module.exports = { router, requireAuth };
