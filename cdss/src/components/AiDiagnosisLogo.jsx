/**
 * AI / neural-network style mark for the Diagnosis module (SVG, scales with size).
 */
export default function AiDiagnosisLogo({ size = 20, className = '', title, ...rest }) {
  return (
    <svg
      className={className}
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden={title ? undefined : true}
      role={title ? 'img' : undefined}
      {...rest}
    >
      {title ? <title>{title}</title> : null}
      {/* Outer neural nodes */}
      <circle cx="16" cy="5" r="2.6" fill="currentColor" />
      <circle cx="27" cy="16" r="2.6" fill="currentColor" />
      <circle cx="16" cy="27" r="2.6" fill="currentColor" />
      <circle cx="5" cy="16" r="2.6" fill="currentColor" />
      {/* Hub */}
      <circle cx="16" cy="16" r="4.2" fill="currentColor" fillOpacity="0.22" />
      <circle cx="16" cy="16" r="3" stroke="currentColor" strokeWidth="1.35" />
      {/* Synapse lines */}
      <path
        d="M16 8.2v3.2M23.8 16h-3.2M16 23.8v-3.2M8.2 16h3.2M11.4 11.4l2.1 2.1M20.5 11.4l-2.1 2.1M20.5 20.5l-2.1-2.1M11.4 20.5l2.1-2.1"
        stroke="currentColor"
        strokeWidth="1.35"
        strokeLinecap="round"
      />
    </svg>
  );
}
