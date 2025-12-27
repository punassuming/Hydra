import { useQuery } from "@tanstack/react-query";
import { Card, List, Tag } from "antd";
import { fetchJobGraph } from "../api/jobs";
import { useActiveDomain } from "../context/ActiveDomainContext";

interface Props {
  jobId: string;
}

export function JobGraphView({ jobId }: Props) {
  const { domain } = useActiveDomain();
  const { data, isLoading } = useQuery({
    queryKey: ["job-graph", domain, jobId],
    queryFn: () => fetchJobGraph(jobId),
    enabled: Boolean(jobId),
  });

  return (
    <Card loading={isLoading}>
      <List
        header="Nodes"
        dataSource={data?.nodes ?? []}
        renderItem={(node) => (
          <List.Item key={node.id}>
            {node.label} <Tag style={{ marginLeft: 8 }}>{node.status}</Tag>
          </List.Item>
        )}
      />
      {data?.edges?.length ? (
        <List
          header="Edges"
          dataSource={data.edges}
          renderItem={(edge, idx) => (
            <List.Item key={`${edge.source}-${edge.target}-${idx}`}>
              {edge.source} → {edge.target}
            </List.Item>
          )}
        />
      ) : (
        <p>No edges defined.</p>
      )}
    </Card>
  );
}
