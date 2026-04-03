import express from "express";
import cors from "cors";

const app = express();
app.use(cors());
app.use(express.json());

app.get("/health", (_req, res) => res.json({ status: "ok" }));

// TODO: /voice/intent, /vision/detect, /catalog/search, /agent/process

app.listen(4000, () => console.log("API running on :4000"));
