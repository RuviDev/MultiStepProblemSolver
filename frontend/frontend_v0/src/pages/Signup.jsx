import React, { useState } from "react";
import { auth } from "../lib/api";
import { useNavigate, Link } from "react-router-dom";

export default function Signup() {
  const nav = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [err, setErr] = useState("");

  const onSubmit = async (e) => {
    e.preventDefault();
    setErr("");
    try {
      await auth.signup(email, password);
      nav("/");
    } catch (e) {
      setErr("Signup failed.");
      console.error(e);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-white">
      <form onSubmit={onSubmit} className="w-full max-w-sm space-y-4 p-6 rounded-2xl border">
        <h1 className="text-xl font-semibold">Create account</h1>
        {err && <div className="text-red-600 text-sm">{err}</div>}
        <div className="space-y-1">
          <label className="text-sm text-gray-600">Email</label>
          <input className="w-full border rounded-lg p-2" type="email" value={email} onChange={(e)=>setEmail(e.target.value)} required />
        </div>
        <div className="space-y-1">
          <label className="text-sm text-gray-600">Password</label>
          <input className="w-full border rounded-lg p-2" type="password" value={password} onChange={(e)=>setPassword(e.target.value)} required />
        </div>
        <button className="w-full bg-gray-900 text-white rounded-lg p-2">Create</button>
        <p className="text-sm text-gray-600">Already have an account? <Link to="/login" className="text-gray-900 underline">Sign in</Link></p>
      </form>
    </div>
  );
}