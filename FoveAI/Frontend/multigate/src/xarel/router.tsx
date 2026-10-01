import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";

// Surface holons
import homepage from "./homepage";
import manifesto from "./manifesto";

// XRLF spatial workspace entry
// (You already have this in your project — we simply route to it)
import XRWorkspace from "../xr/XRWorkspace";

export default function router() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Xarel public surface */}
        <Route path="/" element={<homepage />} />
        <Route path="/manifesto" element={<manifesto />} />

        {/* XRLF spatial machine workspace */}
        <Route path="/xr" element={<XRWorkspace />} />

        {/* Fallback: redirect unknown routes to homepage */}
        <Route path="*" element={<homepage />} />
      </Routes>
    </BrowserRouter>
  );
}
