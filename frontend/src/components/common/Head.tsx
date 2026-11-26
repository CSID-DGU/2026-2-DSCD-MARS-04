export default function Head({ title, lead }: { title: string; lead: string }) {
  return (
    <>
      <h1>{title}</h1>
      <p className="lead">{lead}</p>
    </>
  )
}
