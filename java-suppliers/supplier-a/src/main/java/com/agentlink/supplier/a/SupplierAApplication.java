package com.agentlink.supplier.a;

import com.agentlink.supplier.config.SupplierBeans;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SupplierBeans.class)
public class SupplierAApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupplierAApplication.class, args);
    }
}
