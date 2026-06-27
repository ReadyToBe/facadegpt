import React from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";
import AppShell from "./pages/AppShell.jsx";
import ProjectChatPage from "./pages/ProjectChatPage.jsx";
import SchemeDetailPage from "./pages/SchemeDetailPage.jsx";
import WorkspaceEntryPage from "./pages/WorkspaceEntryPage.jsx";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route element={<AppShell />}>
          <Route path="/" element={<WorkspaceEntryPage />} />
          <Route path="/project/:id/chat" element={<ProjectChatPage />} />
          <Route path="/project/:id/results" element={<ProjectChatPage />} />
          <Route path="/scheme/:id" element={<SchemeDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
