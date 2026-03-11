import { colors } from "../../ui/index.js";

interface DeleteConfirmationProps {
  message: string;
  width: number;
}

export function DeleteConfirmation({ message, width }: DeleteConfirmationProps) {
  return (
    <box flexDirection="column" width={width} paddingLeft={1}>
      <text>
        <span fg={colors.status.warning}>{message}</span>
      </text>
      <box marginTop={1}>
        <text><span fg={colors.text.muted}>Press y to confirm, any other key to cancel</span></text>
      </box>
    </box>
  );
}
