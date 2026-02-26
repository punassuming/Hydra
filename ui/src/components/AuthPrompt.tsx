import { Modal, Input, Typography, Space, message, Checkbox } from "antd";
import { useEffect, useState } from "react";
import { setTokenForDomain } from "../api/client";
import { useActiveDomain } from "../context/ActiveDomainContext";

interface Props {
  open: boolean;
  onClose: () => void;
  onSuccess?: () => void;
}

export function AuthPrompt({ open, onClose, onSuccess }: Props) {
  const [token, setToken] = useState("");
  const [domainInput, setDomainInput] = useState("");
  const [adminMode, setAdminMode] = useState(false);
  const { domain, setDomain } = useActiveDomain();

  useEffect(() => {
    if (!open) return;
    setDomainInput(domain || "prod");
    setToken("");
  }, [open, domain]);

  return (
    <Modal
      open={open}
      title="Sign In"
      closable={false}
      maskClosable={false}
      keyboard={false}
      onCancel={onClose}
      onOk={() => {
        const finalToken = token.trim();
        const finalDomain = domainInput.trim();
        if (!finalToken) {
          message.error("Token required");
          return;
        }
        if (!adminMode && !finalDomain) {
          message.error("Domain required");
          return;
        }
        if (adminMode) {
          setTokenForDomain("admin", finalToken);
          if (finalDomain) {
            setDomain(finalDomain);
          }
          message.success("Admin token saved");
        } else {
          setTokenForDomain(finalDomain, finalToken);
          setDomain(finalDomain);
          message.success(`Token saved for domain ${finalDomain}`);
        }
        onSuccess?.();
        onClose();
      }}
      cancelButtonProps={{ style: { display: "none" } }}
      okText="Authenticate"
    >
      <Space direction="vertical" style={{ width: "100%" }}>
        <Typography.Text>
          Enter domain and token. Domain is required for non-admin authentication.
        </Typography.Text>
        <Input value={domainInput} onChange={(e) => setDomainInput(e.target.value)} placeholder="Domain (e.g. prod)" />
        <Input.Password value={token} onChange={(e) => setToken(e.target.value)} placeholder="Token" />
        <Checkbox checked={adminMode} onChange={(e) => setAdminMode(e.target.checked)}>
          Use admin token
        </Checkbox>
      </Space>
    </Modal>
  );
}
