import { Select, Space, Typography, Button, Input, Tag } from "antd";
import { useEffect, useState } from "react";
import { setActiveDomain as storeDomain, setTokenForDomain, getAdminToken, hasTokenForDomain } from "../api/client";
import { useDomains } from "../hooks/useDomains";
import { useActiveDomain } from "../context/ActiveDomainContext";
import { useTheme } from "../theme";

export function DomainSelector({ onChange }: { onChange?: (domain: string) => void }) {
  const domainOptions = useDomains();
  const { domain: current, setDomain } = useActiveDomain();
  const { colors } = useTheme();
  const [newDomainInput, setNewDomainInput] = useState("");
  const adminToken = getAdminToken();
  const availableDomains = domainOptions.map((o) => o.domain);

  useEffect(() => {
    if (!availableDomains.length || availableDomains.includes(current)) {
      return;
    }
    const fallback = availableDomains.includes("prod") ? "prod" : availableDomains[0];
    storeDomain(fallback);
    setDomain(fallback);
    onChange?.(fallback);
  }, [availableDomains, current, onChange, setDomain]);

  const selectOptions = Array.from(new Set([current, ...domainOptions.map((o) => o.domain)])).map((domain) => {
    const hit = domainOptions.find((o) => o.domain === domain);
    return { label: hit?.label || domain, value: domain };
  });

  const applyDomain = (domain: string) => {
    const trimmed = domain.trim();
    if (!trimmed) return;
    storeDomain(trimmed);
    setDomain(trimmed);
    onChange?.(trimmed);
  };

  return (
    <Space>
      <Space direction="vertical" size={0}>
        <Typography.Text style={{ color: colors.textSecondary }}>Active Domain</Typography.Text>
        <Tag color={hasTokenForDomain(current) ? "green" : "volcano"} style={{ marginTop: 2 }}>
          {hasTokenForDomain(current) ? "Token saved" : "No token"}
        </Tag>
      </Space>
      <Select
        size="small"
        value={current}
        options={selectOptions}
        onChange={applyDomain}
        style={{ minWidth: 160 }}
        showSearch
        dropdownRender={(menu) => (
          <>
            {menu}
            <Space style={{ padding: 8, width: "100%" }}>
              <Input
                size="small"
                value={newDomainInput}
                placeholder="Enter new domain"
                onChange={(e) => setNewDomainInput(e.target.value)}
                onPressEnter={() => {
                  applyDomain(newDomainInput);
                  setNewDomainInput("");
                }}
              />
              <Button
                size="small"
                onClick={() => {
                  applyDomain(newDomainInput);
                  setNewDomainInput("");
                }}
              >
                Use
              </Button>
            </Space>
          </>
        )}
      />
      {adminToken && (
        <Button
          size="small"
          onClick={() => {
            setTokenForDomain(current, adminToken);
            storeDomain(current);
            setDomain(current);
          }}
        >
          Use Admin
        </Button>
      )}
    </Space>
  );
}
