import React, { useState, useEffect, useCallback } from 'react';
import './App.css';

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});
  const [expanded, setExpanded] = useState({});
  const [lightboxImage, setLightboxImage] = useState(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/suggestions`);
      if (!res.ok) throw new Error(`HTTP error! status: ${res.status}`);
      const data = await res.json();
      // Initialize thoughts and expanded states
      const thoughts = {}, exp = {};
      data.forEach(post => { thoughts[post.id] = ''; exp[post.id] = false; });
      setInitialThoughts(thoughts);
      setExpanded(exp);
      // Sort by SMPchat priority
      data.sort((a, b) => {
        const aPri = a.subreddit?.toLowerCase()==='smpchat';
        const bPri = b.subreddit?.toLowerCase()==='smpchat';
        if (aPri && !bPri) return -1;
        if (!aPri && bPri) return 1;
        return a.id.localeCompare(b.id);
      });
      setPendingComments(data);
    } catch (err) {
      console.error('Error fetching suggestions:', err);
    }
  }, [API_URL]);

  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);

  const toggleExpand = id => {
    setExpanded(prev => ({ ...prev, [id]: !prev[id] }));
  };

  const openLightbox = url => setLightboxImage(url);
  const closeLightbox = () => setLightboxImage(null);

  const handleGenerate = async id => {
    const thoughts = initialThoughts[id] || '';
    setPendingComments(prev => prev.map(p => p.id===id ? { ...p, suggestedComment: 'Generating...' } : p));
    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_thought: thoughts })
      });
      if (!res.ok) throw new Error();
      const json = await res.json();
      setPendingComments(prev => prev.map(p => p.id===id ? { ...p, suggestedComment: json.suggestedComment } : p));
    } catch {
      alert('Failed to generate.');
      fetchSuggestions();
    }
  };

  const handleAction = async (id, actionType) => {
    const post = pendingComments.find(p => p.id===id);
    let url = '', opts = {};
    if (actionType === 'approve') {
      if (!post.suggestedComment?.trim()) { alert('Please generate a comment first.'); return; }
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      opts = { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ approved_comment: post.suggestedComment }) };
    }
    if (actionType === 'reject') {
      url = `${API_URL}/suggestions/${id}`;
      opts = { method:'DELETE' };
    }
    if (actionType === 'postDirect') {
      const txt = initialThoughts[id]||'';
      if (!txt.trim()) { alert('Please enter your thoughts.'); return; }
      if (!window.confirm('Post your thoughts directly?')) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      opts = { method:'POST', headers:{ 'Content-Type':'application/json' }, body: JSON.stringify({ direct_comment: txt }) };
    }
    try {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error();
      setPendingComments(prev => prev.filter(p => p.id!==id));
    } catch {
      alert('Action failed.');
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Reddit Comment Review</h1>
      </header>
      <div className="comment-list">
        {pendingComments.length === 0 ? (
          <p>No pending posts to review.</p>
        ) : (
          pendingComments.map(c => (
            <div key={c.id} className="comment-card">
              <div className="card-header">
                <a href={c.redditPostUrl} target="_blank" rel="noopener noreferrer" className="post-title">
                  {c.redditPostTitle}
                </a>
                <span className="subreddit-tag">r/{c.subreddit}</span>
              </div>

              {c.redditPostSelftext && (
                <>
                  <p className={`selftext-preview ${expanded[c.id] ? 'expanded' : ''}`}>{c.redditPostSelftext}</p>
                  <button className="see-more-button" onClick={() => toggleExpand(c.id)}>
                    {expanded[c.id] ? 'Show less' : 'See more...'}
                  </button>
                </>
              )}

              {c.image_urls && c.image_urls.length > 0 && (
                <div className="image-preview-container">
                  {c.image_urls.map((url,i) => (
                    <img
                      key={i}
                      src={url}
                      alt="post"
                      className="post-image-preview"
                      onClick={() => openLightbox(url)}
                    />
                  ))}
                </div>
              )}

              <label className="textarea-label">Your Initial Thoughts:</label>
              <textarea
                className="initial-thoughts-textarea"
                placeholder="Type your brief response."
                rows={2}
                value={initialThoughts[c.id]}
                onChange={e => setInitialThoughts(prev => ({ ...prev, [c.id]: e.target.value }))}
              />

              {c.suggestedComment ? (
                <>
                  <label>Suggested Comment:</label>
                  <textarea
                    className="suggested-textarea"
                    rows={4}
                    value={c.suggestedComment}
                    onChange={e => setPendingComments(prev => prev.map(p => p.id === c.id ? { ...p, suggestedComment: e.target.value } : p))}
                  />
                  <div className="actions">
                    <button className="generate-button" onClick={() => handleAction(c.id, 'approve')}>Approve</button>
                    <button className="post-direct-button" onClick={() => handleAction(c.id, 'reject')}>Reject</button>
                  </div>
                </>
              ) : (
                <div className="actions">
                  <button className="generate-button" onClick={() => handleGenerate(c.id)}>Generate</button>
                  <button className="post-direct-button" onClick={() => handleAction(c.id, 'postDirect')}>Post Direct</button>
                </div>
              )}
            </div>
          ))
        )}
      </div>

      {lightboxImage && (
        <div className="lightbox-overlay active" onClick={closeLightbox}>
          <span className="lightbox-close" onClick={closeLightbox}>&times;</span>
          <img src={lightboxImage} alt="full" />
        </div>
      )}
    </div>
  );
}

export default App;
