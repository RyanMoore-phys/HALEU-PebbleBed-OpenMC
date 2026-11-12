import {
  to = aws_vpc.block
  id = "vpc-0ebdf72fbcc2f9a16"
}

import {
  to = aws_subnet.private
  id = "subnet-0fa758146061ab198"
}

import {
  to = aws_route_table.private
  id = "rtb-0c5ec568e59fe55f9"
}

import {
  to = aws_route_table_association.private
  id = "subnet-0fa758146061ab198/rtb-0c5ec568e59fe55f9"
}