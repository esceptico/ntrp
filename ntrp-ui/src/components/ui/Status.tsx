import { Spinner as InkSpinner } from "@inkjs/ui";
import { Panel } from "./layout/Panel.js";

interface LoadingProps {
  message?: string;
}

export function Loading({ message = "Loading..." }: LoadingProps) {
  return (
    <Panel>
      <InkSpinner label={message} />
    </Panel>
  );
}
