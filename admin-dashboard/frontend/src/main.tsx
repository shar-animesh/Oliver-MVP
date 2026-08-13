// Path: src/main.tsx
// Description: Browser entry point for the Oliver admin dashboard.

import React from "react";
import ReactDOM from "react-dom/client";

import App from "./app";
import "./styles/global.css";

const root = document.getElementById("root");
if (!root) {
    throw new Error("Admin dashboard root element was not found");
}

ReactDOM.createRoot(root).render(
    <React.StrictMode>
        <App />
    </React.StrictMode>,
);
