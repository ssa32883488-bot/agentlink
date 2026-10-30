package com.agentlink.supplier.aip;

import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpMethod;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URI;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;
import java.util.Set;

/**
 * UI / 办公协同仍走 Python ERP（SQLite）；Java 进程对外占端口并反代 /api/**。
 */
@RestController
public class ErpProxyController {
    private static final Set<String> HOP_BY_HOP = Set.of(
            "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
            "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length"
    );

    private final String upstream;

    public ErpProxyController(@Value("${agentlink.erp-upstream:}") String upstream) {
        this.upstream = upstream == null ? "" : upstream.trim().replaceAll("/$", "");
    }

    @RequestMapping("/api/**")
    public void proxyApi(HttpServletRequest request, HttpServletResponse response) throws Exception {
        proxy(request, response);
    }

    @RequestMapping({"/group/**"})
    public void proxyGroup(HttpServletRequest request, HttpServletResponse response) throws Exception {
        proxy(request, response);
    }

    private void proxy(HttpServletRequest request, HttpServletResponse response) throws Exception {
        if (upstream.isEmpty()) {
            response.setStatus(503);
            response.setContentType("application/json;charset=UTF-8");
            response.getWriter().write("{\"error\":\"erp_upstream_not_configured\",\"hint\":\"start Python ERP sidecar\"}");
            return;
        }
        String path = request.getRequestURI();
        String qs = request.getQueryString();
        String target = upstream + path + (qs == null || qs.isBlank() ? "" : "?" + qs);

        HttpURLConnection conn = (HttpURLConnection) URI.create(target).toURL().openConnection();
        conn.setConnectTimeout(10_000);
        conn.setReadTimeout(120_000);
        conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(request.getMethod());
        conn.setDoInput(true);

        Enumeration<String> names = request.getHeaderNames();
        while (names.hasMoreElements()) {
            String name = names.nextElement();
            if (name == null || HOP_BY_HOP.contains(name.toLowerCase())) {
                continue;
            }
            Enumeration<String> values = request.getHeaders(name);
            while (values.hasMoreElements()) {
                conn.addRequestProperty(name, values.nextElement());
            }
        }

        boolean hasBody = HttpMethod.POST.matches(request.getMethod())
                || HttpMethod.PUT.matches(request.getMethod())
                || HttpMethod.PATCH.matches(request.getMethod());
        if (hasBody) {
            conn.setDoOutput(true);
            try (InputStream in = request.getInputStream(); OutputStream out = conn.getOutputStream()) {
                in.transferTo(out);
            }
        }

        int status = conn.getResponseCode();
        response.setStatus(status);
        for (var e : conn.getHeaderFields().entrySet()) {
            String key = e.getKey();
            if (key == null || HOP_BY_HOP.contains(key.toLowerCase())) {
                continue;
            }
            List<String> vals = e.getValue() == null ? Collections.emptyList() : e.getValue();
            for (String v : vals) {
                response.addHeader(key, v);
            }
        }
        InputStream body = status >= 400 ? conn.getErrorStream() : conn.getInputStream();
        if (body != null) {
            try (body; OutputStream out = response.getOutputStream()) {
                body.transferTo(out);
            }
        }
    }
}
