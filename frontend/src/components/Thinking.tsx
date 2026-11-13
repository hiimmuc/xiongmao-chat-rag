import Panda from "./Panda";

export default function Thinking() {
  return (
    <span className="thinking" role="status">
      <Panda size={26} mood="thinking" />
      Thinking
      <span className="typing" aria-hidden="true">
        <i />
        <i />
        <i />
      </span>
    </span>
  );
}
