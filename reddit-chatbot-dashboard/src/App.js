// src/App.js
import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});
  const [darkMode, setDarkMode] = useState(false);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/suggestions`);
      if (!res.ok) throw new Error(`Status ${res.status}`);
      let data = await res.json();
      // sort SMPchat first
      data.sort((a, b) => {
        const aPri = a.subreddit.toLowerCase()==='smpchat';
        const bPri = b.subreddit.toLowerCase()==='smpchat';
        if (aPri && !bPri) return -1;
        if (!aPri && bPri) return 1;
        return parseInt(a.id) - parseInt(b.id);
      });
      setPendingComments(data);
      let thoughts = {};
      data.forEach(p => thoughts[p.id] = '');
      setInitialThoughts(thoughts);
    } catch (err) {
      console.error(err);
    }
  }, [API_URL]);

  useEffect(() => { fetchSuggestions() }, [fetchSuggestions]);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prev => ({ ...prev, [id]: text }));
  };

  // ... your generateSuggestion, action handlers, edit handlers as before ...

  return (
    <div className={darkMode ? 'dark-mode' : ''}>
      {/* Dark mode toggle */}
      <button
        className="toggle-dark button--outline"
        onClick={() => setDarkMode(dm => !dm)}
      >
        {darkMode ? '☀️ Light Mode' : '🌙 Dark Mode'}
      </button>

      <div className="container">
        <header className="App-header">
          <h1>Reddit Comment Review</h1>
        </header>

        {pendingComments.length === 0 ? (
          <p>No pending posts. Run your scraper to fetch new ones.</p>
        ) : pendingComments.map(comment => (
          <div key={comment.id} className="backdrop-glass mb-4">
            <div className="card-header">
              <h3>
                <a href={comment.redditPostUrl} target="_blank" rel="noopener noreferrer">
                  {comment.redditPostTitle}
                </a>
              </h3>
              <span className="subreddit-tag">r/{comment.subreddit}</span>
            </div>

            {comment.redditPostSelftext?.length > 0 &&
              <p className="selftext-preview">
                {comment.redditPostSelftext.slice(0,150)}…
              </p>
            }

            {/* Images if any */}
            {comment.image_urls?.length > 0 && (
              <div className="image-preview-container">
                {comment.image_urls.map((url,i)=>(
                  <img key={i} src={url} alt="" className="post-image-preview" />
                ))}
              </div>
            )}

            <p>Your Initial Thoughts:</p>
            <textarea
              rows={2}
              className="initial-thoughts-textarea"
              placeholder="Type your idea for the AI…"
              value={initialThoughts[comment.id]||''}
              onChange={e => handleInitialThoughtsChange(comment.id, e.target.value)}
            />

            {comment.suggestedComment ? (
              <>
                <p>Suggested Comment:</p>
                <textarea
                  rows={5}
                  value={comment.suggestedComment}
                  onChange={e => handleEdit(comment.id, e.target.value)}
                />
                <div className="actions mt-2">
                  <button className="button button--blue" onClick={() => handleAction(comment.id, 'approve')}>
                    Approve & Send
                  </button>
                  <button className="button button--outline ml-2" onClick={() => handleAction(comment.id, 'reject')}>
                    Reject
                  </button>
                </div>
              </>
            ) : (
              <div className="actions mt-2">
                <button className="button button--blue" onClick={() => handleGenerateSuggestion(comment.id)}>
                  Generate Suggestion
                </button>
                <button className="button button--outline ml-2" onClick={() => handleAction(comment.id, 'postDirect')}>
                  Post My Thoughts
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

export default App;
