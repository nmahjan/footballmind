import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import FootballMind from "./FootballMind.jsx";

createRoot(document.getElementById("root")).render(
  <StrictMode>
    <FootballMind />
  </StrictMode>
);
