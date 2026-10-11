"""
Generates an ultra-dense, multi-panel 1920x1080 enterprise cloud console image.
Includes cluster topology, request waterfall, pod status modal, and error log stream.
"""

from PIL import Image, ImageDraw, ImageFont
from pathlib import Path

def create_observability_dashboard(output_path: str):
    width, height = 1920, 1080
    img = Image.new("RGB", (width, height), color="#0F172A")
    draw = ImageDraw.Draw(img)

    try:
        font_large = ImageFont.truetype("arial.ttf", 26)
        font_med = ImageFont.truetype("arial.ttf", 18)
        font_small = ImageFont.truetype("arial.ttf", 14)
        font_code = ImageFont.truetype("consola.ttf", 13)
        font_code_bold = ImageFont.truetype("consolab.ttf", 14)
    except Exception:
        font_large = font_med = font_small = font_code = font_code_bold = ImageFont.load_default()

    # 1. Top Navigation Bar
    draw.rectangle([0, 0, width, 56], fill="#1E293B", outline="#334155")
    draw.text((24, 16), "KUBERNETES OBSERVABILITY CLUSTER // us-east-1 // PRODUCTION-PRIMARY", fill="#F8FAFC", font=font_med)
    draw.text((1600, 18), "Cluster Health: CRITICAL (3 Pods Evicted)", fill="#EF4444", font=font_small)

    # 2. Left Sidebar (Service Topology)
    draw.rectangle([0, 56, 320, height], fill="#0F172A", outline="#1E293B")
    draw.text((20, 80), "MICROSERVICES (14/16 Operational)", fill="#94A3B8", font=font_small)

    services = [
        ("api-gateway-v2", "ONLINE (240ms)", "#10B981"),
        ("auth-tenant-sso", "ONLINE (45ms)", "#10B981"),
        ("billing-settlement", "DEGRADED (1.4s)", "#F59E0B"),
        ("checkout-orchestrator", "FAILING (504 Timeout)", "#EF4444"),
        ("inventory-catalog", "ONLINE (110ms)", "#10B981"),
        ("notification-worker", "ONLINE (85ms)", "#10B981"),
        ("database-primary-pg", "ONLINE (12ms)", "#10B981"),
    ]

    y_pos = 115
    for s_name, s_status, s_color in services:
        draw.rectangle([16, y_pos, 304, y_pos + 46], fill="#1E293B", outline="#334155")
        draw.text((28, y_pos + 6), s_name, fill="#F8FAFC", font=font_small)
        draw.text((28, y_pos + 24), s_status, fill=s_color, font=font_code)
        y_pos += 56

    # 3. Main Center Panel: Distributed Trace Waterfall
    draw.rectangle([340, 76, 1380, 580], fill="#1E293B", outline="#334155")
    draw.text((364, 96), "Trace ID: 4bf92f3577b34da6a3ce929d0e0e4736 | Span Count: 14 | Duration: 30,004ms (EXCEEDED)", fill="#F8FAFC", font=font_med)

    # Trace Spans Waterfall
    spans = [
        ("GET /api/v3/checkout/order-process", 0, 750, "#3B82F6", "200 OK (Envoy Ingress)"),
        ("  auth.validate_bearer_jwt()", 40, 180, "#10B981", "200 OK (45ms)"),
        ("  tenant.enforce_rate_limit()", 190, 240, "#10B981", "200 OK (12ms)"),
        ("  checkout.orchestrate_payment()", 250, 960, "#EF4444", "DEADLINE_EXCEEDED (30,000ms)"),
        ("    grpc.PaymentService.Authorize()", 260, 950, "#EF4444", "Status(StatusCode.UNAVAILABLE)"),
        ("      pg_pool.acquire_connection()", 270, 940, "#DC2626", "DeadlockDetectedError: Lock Timeout"),
    ]

    span_y = 145
    for span_name, start_x, end_x, color, note in spans:
        draw.rectangle([364, span_y, 1356, span_y + 48], fill="#0F172A", outline="#334155")
        draw.text((376, span_y + 6), span_name, fill="#E2E8F0", font=font_code_bold)
        # Bar
        bar_left = 720 + start_x // 2
        bar_right = 720 + end_x // 2
        draw.rectangle([bar_left, span_y + 12, bar_right, span_y + 32], fill=color)
        draw.text((1050, span_y + 14), note, fill=color, font=font_code)
        span_y += 56

    # 4. Critical Error Modal Dialog (Prompt Focus)
    modal_left, modal_top = 540, 230
    modal_right, modal_bottom = 1260, 480
    draw.rectangle([modal_left, modal_top, modal_right, modal_bottom], fill="#0F172A", outline="#EF4444", width=3)
    draw.rectangle([modal_left, modal_top, modal_right, modal_top + 46], fill="#7F1D1D")
    draw.text((modal_left + 18, modal_top + 12), "CRITICAL ALERT: HTTP 504 GATEWAY TIMEOUT / DEADLOCK DETECTED", fill="#FFFFFF", font=font_med)

    draw.text(
        (modal_left + 24, modal_top + 62),
        "Incident Ref: INC-98124\n"
        "Root Cause: Deadlock on customer_ledger_entries table during concurrent schema migration.\n"
        "Failing Host: pod/checkout-orchestrator-7d8b9f-x9w2q in namespace prod-core.\n"
        "Action Required: Terminate lingering transaction PID 48192 or restart pod replica.",
        fill="#F8FAFC",
        font=font_small,
    )

    # Modal Action Button
    draw.rectangle([modal_left + 24, modal_bottom - 50, modal_left + 260, modal_bottom - 16], fill="#DC2626")
    draw.text((modal_left + 42, modal_bottom - 42), "KILL TRANSACTION PID 48192", fill="#FFFFFF", font=font_med)

    # 5. Right Panel: Metrics
    draw.rectangle([1400, 76, 1900, 580], fill="#1E293B", outline="#334155")
    draw.text((1420, 96), "CLUSTER RESOURCE PRESSURE", fill="#F8FAFC", font=font_med)
    draw.text((1420, 140), "CPU Throttling: 92.4% (8 cores pinned)", fill="#EF4444", font=font_small)
    draw.text((1420, 180), "Connection Pool: 200/200 (100% EXHAUSTED)", fill="#EF4444", font=font_small)
    draw.text((1420, 220), "Active Deadlocks: 4 detected", fill="#F59E0B", font=font_small)
    draw.text((1420, 260), "Kafka Consumer Lag: 18,420 msgs", fill="#F59E0B", font=font_small)
    draw.text((1420, 300), "Egress Bandwidth: 1.4 Gbps", fill="#10B981", font=font_small)

    # 6. Bottom Console Log Pane
    draw.rectangle([340, 600, 1900, 1050], fill="#0A0F1D", outline="#1E293B")
    draw.text((364, 616), "LIVE CONTAINER LOG STREAM: pod/checkout-orchestrator-7d8b9f-x9w2q", fill="#94A3B8", font=font_med)

    logs = [
        ("2026-10-11T01:14:22.102Z [WARN]  [pool] Connection pool acquisition delay exceeded 5000ms threshold", "#F59E0B"),
        ("2026-10-11T01:14:23.409Z [ERROR] [asyncpg] deadlock detected: Process 48192 waits for ExclusiveLock on relation 189204", "#EF4444"),
        ("2026-10-11T01:14:25.801Z [ERROR] [grpc] rpc error: code = Unavailable desc = transport is closing due to pool starvation", "#EF4444"),
        ("2026-10-11T01:14:27.114Z [FATAL] [envoy] upstream request timeout: 504 Gateway Timeout downstream IP 10.244.3.18", "#DC2626"),
        ("2026-10-11T01:14:28.002Z [INFO]  [k8s] Liveness probe failed for container checkout-orchestrator. Restarting in 10s...", "#F59E0B"),
    ]

    log_y = 654
    for log_line, log_color in logs:
        draw.text((364, log_y), log_line, fill=log_color, font=font_code)
        log_y += 34

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=95)
    print(f"Generated enterprise observability dashboard screenshot at: {output_path}")

if __name__ == "__main__":
    create_observability_dashboard("benchmark/scenarios/ui_bug_screenshot/login_screen.png")
