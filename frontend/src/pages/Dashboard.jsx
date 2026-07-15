import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import Footer from "../components/Footer";
import { supabase } from "../lib/supabaseClient";
import { api } from "../lib/api";

const TRACKS = [
  {
    id: "behavioral",
    name: "Behavioral",
    description: "Practice STAR-method answers to common behavioral questions.",
    accent: "bg-amber/15 text-amber"
  },
  {
    id: "technical",
    name: "Technical",
    description: "Talk through a coding problem with a live editor and execution.",
    accent: "bg-sage/15 text-sage"
  },
  {
    id: "system-design",
    name: "System design",
    description: "Reason out loud about architecture, trade-offs, and scale.",
    accent: "bg-coral/15 text-coral"
  }
];

export default function Dashboard() {
  const navigate = useNavigate();
  const [sessions, setSessions] = useState([]);
  const [selectedTrack, setSelectedTrack] = useState(null);
  const [jobDescription, setJobDescription] = useState("");
  const jdRef = useRef(null);

  useEffect(() => {
    if (selectedTrack) jdRef.current?.focus();
  }, [selectedTrack]);

  const handleStartSession = () => {
    if (jobDescription.trim()) sessionStorage.setItem("interview_jd", jobDescription.trim());
    else sessionStorage.removeItem("interview_jd");
    navigate(`/interview?track=${selectedTrack}`);
  };
  const [loading, setLoading] = useState(true);
  const [userEmail, setUserEmail] = useState("");
  const [deletingId, setDeletingId] = useState(null);
  const [confirmingDeleteAll, setConfirmingDeleteAll] = useState(false);
  const [deletingAll, setDeletingAll] = useState(false);
  const [deleteAllError, setDeleteAllError] = useState(null);

  useEffect(() => {
    let mounted = true;

    async function load() {
      const { data: userData } = await supabase.auth.getUser();
      if (mounted) setUserEmail(userData?.user?.email ?? "");

      const userId = userData?.user?.id;
      if (!userId) {
        if (mounted) setLoading(false);
        return;
      }

      const { data, error } = await supabase
        .from("sessions")
        .select("id, track, role, overall_score, created_at, status")
        .eq("user_id", userId)
        .order("created_at", { ascending: false })
        .limit(10);

      if (!error && mounted) setSessions(data ?? []);
      if (mounted) setLoading(false);
    }

    load();
    return () => {
      mounted = false;
    };
  }, []);

  const handleDelete = async (sessionId) => {
    if (!window.confirm("Delete this session and its transcript? This cannot be undone.")) return;
    setDeletingId(sessionId);
    try {
      await api.deleteSession(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
    } catch {
      alert("Failed to delete session. Please try again.");
    } finally {
      setDeletingId(null);
    }
  };

  const handleDeleteAll = async () => {
    setDeletingAll(true);
    setDeleteAllError(null);
    try {
      await api.deleteAllSessions();
      setSessions([]);
      setConfirmingDeleteAll(false);
    } catch {
      setDeleteAllError("Couldn't delete your sessions. Nothing was changed — please try again.");
    } finally {
      setDeletingAll(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col">
      <Navbar />
      <main className="flex-1">
        <section className="mx-auto max-w-6xl px-6 py-12">
          <p className="text-sm text-mute">Signed in as {userEmail}</p>
          <h1 className="mt-2 font-display text-4xl tracking-tight">
            Ready for your next session?
          </h1>

          <div className="mt-10 grid gap-6 sm:grid-cols-3">
            {TRACKS.map((track) => (
              <button
                key={track.id}
                onClick={() => { setSelectedTrack(track.id); setJobDescription(""); }}
                className="rounded-2xl border border-white/10 bg-panel p-6 text-left transition hover:border-amber/40"
              >
                <span className={`inline-flex rounded-full px-3 py-1 text-xs font-medium ${track.accent}`}>
                  {track.name}
                </span>
                <p className="mt-4 text-sm text-mute">{track.description}</p>
                <span className="mt-6 inline-block text-sm text-amber">Start session &rarr;</span>
              </button>
            ))}
          </div>

          {selectedTrack && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
              onClick={(e) => { if (e.target === e.currentTarget) setSelectedTrack(null); }}
            >
              <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-panel p-6 shadow-xl">
                <div className="flex items-center justify-between">
                  <h2 className="font-display text-xl">
                    {TRACKS.find((t) => t.id === selectedTrack)?.name} interview
                  </h2>
                  <button onClick={() => setSelectedTrack(null)} className="text-mute hover:text-cream">✕</button>
                </div>
                <p className="mt-1 text-sm text-mute">
                  Paste a job description to tailor questions to the role — or leave blank for a general interview.
                </p>
                <textarea
                  ref={jdRef}
                  value={jobDescription}
                  onChange={(e) => setJobDescription(e.target.value)}
                  placeholder="Paste job description here (optional)..."
                  rows={7}
                  maxLength={5000}
                  className="mt-4 w-full resize-none rounded-xl border border-white/10 bg-panelLight/40 px-4 py-3 text-sm text-cream outline-none placeholder:text-mute/50 focus:border-amber/40"
                />
                {jobDescription.length > 0 && (
                  <p className="mt-1 text-right text-xs text-mute">{jobDescription.length} / 5000</p>
                )}
                <div className="mt-4 flex items-center justify-end gap-3">
                  <button
                    onClick={() => setSelectedTrack(null)}
                    className="rounded-full border border-white/10 px-4 py-2 text-sm text-mute transition hover:text-cream"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleStartSession}
                    className="rounded-full bg-amber px-5 py-2 text-sm font-medium text-ink transition hover:bg-amberDark"
                  >
                    Start session
                  </button>
                </div>
              </div>
            </div>
          )}

          {confirmingDeleteAll && (
            <div
              className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
              onClick={(e) => { if (e.target === e.currentTarget && !deletingAll) setConfirmingDeleteAll(false); }}
            >
              <div className="w-full max-w-lg rounded-2xl border border-white/10 bg-panel p-6 shadow-xl">
                <div className="flex items-center justify-between">
                  <h2 className="font-display text-xl">Delete all sessions?</h2>
                  <button
                    onClick={() => setConfirmingDeleteAll(false)}
                    disabled={deletingAll}
                    className="text-mute transition hover:text-cream disabled:opacity-50"
                  >
                    ✕
                  </button>
                </div>
                {/* The table above is capped at the 10 most recent, so it is not a
                    preview of what gets deleted — say so rather than name a count. */}
                <p className="mt-3 text-sm text-mute">
                  This permanently deletes <strong className="text-cream">every session on your account</strong>,
                  including any older ones not listed here, along with their full transcripts and scores.
                </p>
                <p className="mt-2 text-sm text-coral">This cannot be undone.</p>
                {deleteAllError && <p className="mt-3 text-sm text-coral">{deleteAllError}</p>}
                <div className="mt-5 flex items-center justify-end gap-3">
                  <button
                    onClick={() => setConfirmingDeleteAll(false)}
                    disabled={deletingAll}
                    className="rounded-full border border-white/10 px-4 py-2 text-sm text-mute transition hover:text-cream disabled:opacity-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleDeleteAll}
                    disabled={deletingAll}
                    className="rounded-full bg-coral px-5 py-2 text-sm font-medium text-ink transition hover:bg-coral/80 disabled:opacity-50"
                  >
                    {deletingAll ? "Deleting..." : "Delete everything"}
                  </button>
                </div>
              </div>
            </div>
          )}

          <div className="mt-16">
            <div className="flex items-center justify-between gap-4">
              <h2 className="font-display text-2xl tracking-tight">Recent sessions</h2>
              {sessions.length > 0 && (
                <button
                  onClick={() => { setDeleteAllError(null); setConfirmingDeleteAll(true); }}
                  className="rounded-full border border-white/10 px-4 py-1.5 text-xs text-mute transition hover:border-coral/40 hover:text-coral"
                >
                  Delete all
                </button>
              )}
            </div>

            {loading ? (
              <p className="mt-4 text-sm text-mute">Loading...</p>
            ) : sessions.length === 0 ? (
              <div className="mt-4 rounded-2xl border border-dashed border-white/10 p-8 text-center text-sm text-mute">
                No sessions yet. Pick a track above to run your first mock interview.
              </div>
            ) : (
              <div className="mt-4 overflow-hidden rounded-2xl border border-white/10">
                <table className="w-full text-left text-sm">
                  <thead className="bg-panel text-mute">
                    <tr>
                      <th className="px-4 py-3 font-medium">Track</th>
                      <th className="px-4 py-3 font-medium">Role</th>
                      <th className="px-4 py-3 font-medium">Score</th>
                      <th className="px-4 py-3 font-medium">Status</th>
                      <th className="px-4 py-3 font-medium">Date</th>
                      <th className="px-4 py-3 font-medium" colSpan={2}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sessions.map((s) => (
                      <tr key={s.id} className="border-t border-white/5">
                        <td className="px-4 py-3 capitalize">{s.track}</td>
                        <td className="px-4 py-3 text-mute">{s.role || "—"}</td>
                        <td className="px-4 py-3">
                          {s.overall_score != null ? `${s.overall_score}/10` : "—"}
                        </td>
                        <td className="px-4 py-3 text-mute capitalize">{s.status}</td>
                        <td className="px-4 py-3 text-mute">
                          {new Date(s.created_at).toLocaleDateString()}
                        </td>
                        <td className="px-4 py-3 text-right">
                          <Link to={`/results/${s.id}`} className="text-amber hover:underline">
                            View
                          </Link>
                        </td>
                        <td className="px-4 py-3 text-right">
                          <button
                            onClick={() => handleDelete(s.id)}
                            disabled={deletingId === s.id}
                            className="text-sm text-mute transition hover:text-coral disabled:opacity-50"
                          >
                            {deletingId === s.id ? "Deleting..." : "Delete"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </section>
      </main>
      <Footer />
    </div>
  );
}
