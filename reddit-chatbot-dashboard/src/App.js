import React, { useState, useEffect, useCallback } from 'react';
import './App.css'; 

function App() {
  const [pendingComments, setPendingComments] = useState([]);
  const [initialThoughts, setInitialThoughts] = useState({});
  const [lightboxImage, setLightboxImage] = useState(null);

  const API_URL = process.env.REACT_APP_API_URL || 'http://localhost:5000';

  const fetchSuggestions = useCallback(async () => {
    try {
      const response = await fetch(`${API_URL}/suggestions`);
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      let data = await response.json();

      // Same sorting logic
      data.sort((a, b) => {
        const aIsPriority = a.subreddit?.toLowerCase() === 'smpchat';
        const bIsPriority = b.subreddit?.toLowerCase() === 'smpchat';
        if (aIsPriority && !bIsPriority) return -1;
        if (!aIsPriority && bIsPriority) return 1;
        return parseInt(a.id) - parseInt(b.id);
      });

      setPendingComments(data);
      const thoughts = {};
      data.forEach(post => thoughts[post.id] = '');
      setInitialThoughts(thoughts);
    } catch (err) {
      console.error('Error fetching suggestions:', err);
    }
  }, [API_URL]);

  useEffect(() => { fetchSuggestions(); }, [fetchSuggestions]);

  const openLightbox = url => setLightboxImage(url);
  const closeLightbox = () => setLightboxImage(null);

  const handleInitialThoughtsChange = (id, text) => {
    setInitialThoughts(prev => ({ ...prev, [id]: text }));
  };

  const handleGenerate = async id => {
    const thoughts = initialThoughts[id] || '';
    setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: 'Generating...' } : p));
    try {
      const res = await fetch(`${API_URL}/suggestions/${id}/generate`, {
        method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ user_thought: thoughts })
      });
      if (!res.ok) throw new Error();
      const json = await res.json();
      setPendingComments(prev => prev.map(p => p.id === id ? { ...p, suggestedComment: json.suggestedComment } : p));
    } catch {
      alert('Failed to generate.');
      fetchSuggestions();
    }
  };

  const handleAction = async (id, actionType) => {
    const post = pendingComments.find(p => p.id === id);
    let url='', opts={};
    if (actionType === 'approve') {
      if (!post.suggestedComment) { alert('Generate first.'); return; }
      url = `${API_URL}/suggestions/${id}/approve-and-post`;
      opts = { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ approved_comment: post.suggestedComment }) };
    }
    if (actionType === 'reject') { url = `${API_URL}/suggestions/${id}`; opts = { method:'DELETE' }; }
    if (actionType === 'postDirect') {
      const txt = initialThoughts[id]; if (!txt.trim()){ alert('Type thoughts.'); return; }
      if (!window.confirm('Post your thoughts directly?')) return;
      url = `${API_URL}/suggestions/${id}/post-direct`;
      opts = { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ direct_comment: txt }) };
    }
    try {
      const res = await fetch(url, opts);
      if (!res.ok) throw new Error();
      setPendingComments(prev => prev.filter(p => p.id !== id));
    } catch (err) {
      alert('Action failed.');
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1 style={{ fontSize: '1.5rem' }}>Reddit Comment Review</h1>
      </header>
      <div className="comment-list container">
        {pendingComments.length === 0 ? (
          <p>No pending posts.</p>
        ) : pendingComments.map(c => (
          <div key={c.id} className="backdrop-glass card mb-4">
            <div className="card-header">
              <a href={c.redditPostUrl} target="_blank" rel="noopener noreferrer" className="post-title">{c.redditPostTitle}</a>
              <div className="post-meta">{new Date(parseFloat(c.created_utc)*1000).toLocaleString(undefined,{hour:'numeric',minute:'2-digit'})}</div>
            </div>
            {c.image_urls && c.image_urls.length > 0 && (
              <div className="image-preview-container">
                {c.image_urls.map((url,i)=>(
                  <img key={i} src={url} alt="post" onClick={()=>openLightbox(url)} className="post-image-preview" />
                ))}
              </div>
            )}
            <textarea className="initial-thoughts-textarea" placeholder="Your thoughts..." rows={2}
              value={initialThoughts[c.id]||''} onChange={e=>handleInitialThoughtsChange(c.id,e.target.value)} />
            {c.suggestedComment ? (
              <>
                <textarea className="suggested-textarea" rows={4} value={c.suggestedComment}
                  onChange={e=>setPendingComments(prev=>prev.map(p=>p.id===c.id?{...p,suggestedComment:e.target.value}:p))} />
                <div className="actions">
                  <button className="button button--blue" onClick={()=>handleAction(c.id,'approve')}>Approve</button>
                  <button className="button button--outline" onClick={()=>handleAction(c.id,'reject')}>Reject</button>
                </div>
              </>
            ) : (
              <div className="actions">
                <button className="button button--blue" onClick={()=>handleGenerate(c.id)}>Generate</button>
                <button className="button button--outline" onClick={()=>handleAction(c.id,'postDirect')}>Post Direct</button>
              </div>
            )}
          </div>
        ))}
      </div>

      {lightboxImage && (
        <div className="lightbox-overlay" onClick={closeLightbox}>
          <img src={lightboxImage} alt="full" className="lightbox-image" />
        </div>
      )}
    </div>
  );
}

export default App;
