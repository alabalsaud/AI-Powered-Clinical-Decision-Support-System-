/**
 * Sidebar / settings avatar: photo from user.profile_image or initials.
 */
export default function UserAvatar({ user, size = 34, className = '' }) {
  const src = user?.profile_image;
  const label = (user?.full_name || user?.name || user?.username || 'DR').slice(0, 2).toUpperCase();
  const px = `${size}px`;
  if (src && String(src).startsWith('data:image/')) {
    return (
      <img
        src={src}
        alt=""
        className={`user-avatar user-avatar-photo ${className}`}
        width={size}
        height={size}
        style={{ width: px, height: px }}
      />
    );
  }
  return (
    <div
      className={`user-avatar ${className}`}
      style={{ width: px, height: px, fontSize: Math.max(11, Math.round(size * 0.38)) }}
    >
      {label}
    </div>
  );
}
