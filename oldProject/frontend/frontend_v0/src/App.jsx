import "./App.css";
import { BrowserRouter, Routes, Route, Navigate, useParams, useLocation } from "react-router-dom";
import AiChat from "./app/aiChat";
import { useEffect, useState } from "react";
import { chats } from "./lib/api";
import Login from "./pages/Login";
import Signup from "./pages/Signup";
import { getTokens } from "./lib/api";

function RequireAuth({ children }) {
  const tokens = getTokens();
  const authed = !!tokens?.access_token;
  const loc = useLocation();
  if (!authed) return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  return children;
}

function ChatRedirect() {
  const [to, setTo] = useState(null);
  useEffect(() => {
    (async () => {
      const c = await chats.create();
      setTo(`/${c.id}`);
    })().catch(console.error);
  }, []);
  if (!to) return null;
  return <Navigate to={to} replace />;
}

function ChatWithId() {
  const { chatId } = useParams();
  return <AiChat chatId={chatId} />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/signup" element={<Signup />} />
        <Route
          path="/"
          element={
            <RequireAuth>
              <ChatRedirect />
            </RequireAuth>
          }
        />
        <Route
          path="/:chatId"
          element={
            <RequireAuth>
              <ChatWithId />
            </RequireAuth>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}

export default App;