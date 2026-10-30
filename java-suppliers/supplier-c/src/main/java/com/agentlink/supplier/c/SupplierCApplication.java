package com.agentlink.supplier.c;

import com.agentlink.supplier.config.SupplierBeans;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Import;

@SpringBootApplication
@Import(SupplierBeans.class)
public class SupplierCApplication {
    public static void main(String[] args) {
        SpringApplication.run(SupplierCApplication.class, args);
    }
}
