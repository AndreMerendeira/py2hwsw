// SPDX-FileCopyrightText: 2025 IObundle
//
// SPDX-License-Identifier: MIT

`timescale 1ns / 1ps
`include "iob_asym_converter_conf.vh"

module iob_asym_converter #(
   `include "iob_asym_converter_params.vs"
) (
   `include "iob_asym_converter_io.vs"
);

   `include "iob_functions.vs"

   //Data is valid after read enable
   wire r_data_valid_reg;
   iob_reg_car #(
      .DATA_W (1),
      .RST_VAL(1'b0)
   ) r_data_valid_reg_inst (
      `include "iob_asym_converter_iob_clk_s_s_portmap.vs"
      .rst_i (rst_i),
      .data_i(r_en_i),
      .data_o(r_data_valid_reg)
   );

   //Register read data from the memory
   wire [MAXDATA_W-1:0] r_data_reg;
   iob_reg_care #(
      .DATA_W (MAXDATA_W),
      .RST_VAL({MAXDATA_W{1'd0}})
   ) r_data_reg_inst (
      `include "iob_asym_converter_iob_clk_s_s_portmap.vs"
      .rst_i (rst_i),
      .en_i  (r_data_valid_reg),
      .data_i(ext_mem_r_data_i),
      .data_o(r_data_reg)
   );

   reg [MAXDATA_W-1:0] r_data_int;
   always @* begin
      if (r_data_valid_reg) begin
         r_data_int = ext_mem_r_data_i;
      end else begin
         r_data_int = r_data_reg;
      end
   end

   //Generate the RAM based on the parameters
   generate
      if (W_DATA_W > R_DATA_W) begin : g_write_wider
         //memory write port
         assign ext_mem_w_en_o   = {R{w_en_i}};
         assign ext_mem_w_addr_o = w_addr_i;
         assign ext_mem_w_data_o = w_data_i;

         //register to hold the LSBs of r_addr
         wire [$clog2(R)-1:0] r_addr_lsbs_reg;
         iob_reg_cae #(
            .DATA_W ($clog2(R)),
            .RST_VAL({$clog2(R) {1'd0}})
         ) r_addr_reg_inst (
            `include "iob_asym_converter_iob_clk_s_s_portmap.vs"
            .en_i  (r_en_i),
            .data_i(r_addr_i[$clog2(R)-1:0]),
            .data_o(r_addr_lsbs_reg)
         );

         //memory read port
         assign ext_mem_r_addr_o = r_addr_i[R_ADDR_W-1:$clog2(R)];

         wire [W_DATA_W-1:0] r_data;
         if (BIG_ENDIAN) begin : g_big_endian
            assign ext_mem_r_en_o = {{(R - 1) {1'd0}}, r_en_i} << ((R - 1) - r_addr_i[$clog2(
                R
            )-1:0]);
            assign r_data = r_data_int >> (((R - 1) - r_addr_lsbs_reg) * R_DATA_W);
         end else begin : g_little_endian
            assign ext_mem_r_en_o = {{(R - 1) {1'd0}}, r_en_i} << r_addr_i[$clog2(R)-1:0];
            assign r_data         = r_data_int >> (r_addr_lsbs_reg * R_DATA_W);
         end
         assign r_data_o = r_data[0+:R_DATA_W];

      end else if (W_DATA_W < R_DATA_W) begin : g_read_wider
         //memory write port
         assign ext_mem_w_en_o = {{(R - 1) {1'd0}}, w_en_i} << w_addr_i[$clog2(R)-1:0];
         assign ext_mem_w_data_o = {{(R_DATA_W - W_DATA_W) {1'd0}}, w_data_i} << (w_addr_i[$clog2(
             R
         )-1:0] * W_DATA_W);
         assign ext_mem_w_addr_o = w_addr_i[W_ADDR_W-1:$clog2(R)];

         //memory read port
         assign ext_mem_r_en_o = {R{r_en_i}};
         assign ext_mem_r_addr_o = r_addr_i;
         if (BIG_ENDIAN) begin : g_big_endian
            genvar data_sel;
            for (data_sel = 0; data_sel < R; data_sel = data_sel + 1) begin : gen_r_data
               assign r_data_o[data_sel * W_DATA_W +: W_DATA_W] =
                        r_data_int[((R - 1) - data_sel) * W_DATA_W +: W_DATA_W];
            end
         end else begin : g_little_endian
            assign r_data_o = r_data_int;
         end

      end else begin : g_same_width
         //W_DATA_W == R_DATA_W
         //memory write port
         assign ext_mem_w_en_o   = w_en_i;
         assign ext_mem_w_addr_o = w_addr_i;
         assign ext_mem_w_data_o = w_data_i;

         //memory read port
         assign ext_mem_r_en_o   = r_en_i;
         assign ext_mem_r_addr_o = r_addr_i;
         assign r_data_o         = r_data_int;
      end
   endgenerate
endmodule

