package com.agentlink.supplier.b;

import com.agentlink.supplier.config.SupplierBeans;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SupplierBeans.class)
public class SupplierBApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupplierBApplication.class, args);
    }
}
