import React, { /* … */ } from 'react';
// at top of file
function formatTimestamp(utcSeconds) {
  const d = new Date(utcSeconds * 1000);
  return d.toLocaleDateString('en-US', {
    month: 'short', day: 'numeric', year: 'numeric'
  })
  + ' '
  + d.toLocaleTimeString('en-US', {
    hour: 'numeric', minute: '2-digit', hour12: true
  });
}

// inside your .map of pendingComments:
{pendingComments.map(comment => (
  <div key={comment.id} className="comment-card">
    <div className="card-header">
      <h3>
        <a href={comment.redditPostUrl} target="_blank" rel="noopener noreferrer">
          {comment.redditPostTitle}
        </a>
      </h3>
      <span className="subreddit-tag">r/{comment.subreddit}</span>
    </div>

    {/* New timestamp line */}
    <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
      {formatTimestamp(comment.created_utc)}
    </div>

    {/* … rest of your rendering (selftext, images, textarea, buttons) */}
  </div>
))}
