import { OrderInspector } from "@/components/OrderInspector";

export default async function OrderPage({
  params,
}: {
  params: Promise<{ runId: string; orderId: string }>;
}) {
  const { runId, orderId } = await params;
  return <OrderInspector runId={runId} orderId={orderId} />;
}
